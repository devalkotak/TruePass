# setup.py (Fixed imports)
from app import app, db, User
from werkzeug.security import generate_password_hash

def init_db():
    with app.app_context():
        # 1. Ensure tables exist
        db.create_all()
        
        # 2. Check if Admin exists
        if User.query.filter_by(role='admin').first():
            print("Admin already exists. Skipping seed.")
            return

        # 3. Create Hardcoded Admin
        admin = User(
            username='admin', 
            password_hash=generate_password_hash('admin123'), 
            role='admin', 
            balance=0.0
        )
        # Give admin a distinct wallet address
        admin.wallet_address = "0xADMIN_ROOT_AUTHORITY"
        
        db.session.add(admin)
        db.session.commit()
        
        print("-----------------------------------")
        print("SYSTEM INITIALIZED")
        print("Admin Credentials: admin / devaldeval")
        print("-----------------------------------")

if __name__ == '__main__':
    init_db()