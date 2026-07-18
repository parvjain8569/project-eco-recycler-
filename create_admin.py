from app import app, db, User

def make_user_admin():
    email = input("Enter the email of the user you want to make admin: ")
    
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        
        if user:
            user.is_admin = True
            db.session.commit()
            print(f"Success! User {user.name} ({user.email}) is now an Admin.")
        else:
            print("Error: User with that email not found.")

if __name__ == "__main__":
    make_user_admin()
