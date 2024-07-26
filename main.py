from __future__ import annotations
from datetime import date
from typing import List
import os

from flask import Flask, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, inspect, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

'''
Make sure the required packages are installed: 
Open the Terminal in PyCharm (bottom left). 

On Windows type:
python -m pip install -r requirements.txt

On MacOS type:
pip3 install -r requirements.txt

This will install the packages from the requirements.txt for this project.
'''

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)

# CREATE DATABASE
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", "sqlite:///posts.db")
db = SQLAlchemy(app)
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


# TODO: Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# TODO: Create a User table for all your registered users.
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(25), nullable=False)
    blogpost: Mapped[List[BlogPost]] = relationship(back_populates="author")
    comment: Mapped[List[BlogComment]] = relationship(back_populates="commentator")

    def set_password(self, password):
        # noinspection PyTypeChecker
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped[User] = relationship(back_populates="blogpost")
    comment: Mapped[List[BlogComment]] = relationship(back_populates="blogpost")


class BlogComment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    commentator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    post_id: Mapped[int] = mapped_column(ForeignKey("blog_posts.id"))
    commentator: Mapped[User] = relationship(back_populates="comment")
    blogpost: Mapped[List[BlogPost]] = relationship(back_populates="comment")


def create_table():
    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table('user') or not inspector.has_table('blog_posts'):
            db.create_all()


def admin_only(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ("RootUser", "Admin"):
            flash("Elevated access is required for this page. Please log in as an admin", "error")
            return redirect(url_for('login', next='/admin'))
        return func(*args, **kwargs)
    return decorated_function


@login_manager.user_loader
def load_user(user_id):
    return User.query.filter_by(id=int(user_id)).first()


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["GET", "POST"])
def register():
    register_form = RegisterForm()
    if register_form.validate_on_submit():
        user_email = register_form.email.data
        user_password = register_form.password.data
        user_name = register_form.name.data
        if not User.query.filter_by(email=user_email).first():
            if not User.query.first():
                # noinspection PyArgumentList
                new_user = User(name=user_name, email=user_email, role="RootUser")
            else:
                # noinspection PyArgumentList
                new_user = User(name=user_name, email=user_email, role="Visitor")
            new_user.set_password(user_password)
            db.session.add(new_user)
            db.session.commit()

            login_user(new_user)
            return redirect(url_for('get_all_posts'))
        else:
            flash("You've already registered with that email. Log in instead!", "error")
            return redirect(url_for('login'))
    return render_template("register.html", form=register_form)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=["GET", "POST"])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        input_email = login_form.email.data
        input_password = login_form.password.data
        next_ = request.args.get('next')

        matching_user = User.query.filter_by(email=input_email).first()
        if next_ == "/admin":
            if (matching_user and matching_user.check_password(input_password)
                    and matching_user.role in ("RootUser", "Admin")):
                login_user(matching_user)
                return redirect(next_ or url_for('admin'))
            else:
                flash("Elevated access is required for this page. Please log in as an admin", "error")
        else:
            if matching_user and matching_user.check_password(input_password):
                login_user(matching_user)
                return redirect(next_ or url_for('get_all_posts'))
            else:
                flash("Incorrect credentials. Please try again.", "error")
    return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/admin')
@login_required
@admin_only
def admin():
    page = request.args.get('page', 1, type=int)
    items_per_page = 5  # Number of items per page
    all_users = User.query.paginate(page=page, per_page=items_per_page)
    return render_template('admin.html', users=all_users)


@app.route('/change_role', methods=["POST"])
@login_required
@admin_only
def change_role():
    user_id = request.args.get('user_id')
    user_role_change = db.get_or_404(User, user_id)
    if user_role_change.role == "Admin":
        user_role_change.role = "Visitor"
    else:
        user_role_change.role = "Admin"
    db.session.commit()

    return redirect(url_for('admin'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    if form.validate_on_submit():
        if current_user.is_authenticated:
            new_comment = BlogComment(
                text=form.comment.data,
                commentator=current_user,
                blogpost=requested_post
            )
            db.session.add(new_comment)
            db.session.commit()
            form = CommentForm(formdata=None)
        else:
            flash("You need to log in or register to comment", "error")
            return redirect(url_for('login', next=f"/post/{post_id}"))
    post_comments = BlogComment.query.filter_by(post_id=post_id).order_by(BlogComment.id.desc()).all()
    return render_template("post.html", post=requested_post, form=form, comments=post_comments)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    create_table()
    app.run(debug=False, port=5002)
