from app import app, db, User
from werkzeug.security import generate_password_hash

def init_db():
    with app.app_context():
        # Veritabanı tablolarını oluştur
        db.create_all()
        
        # Admin kullanıcısı kontrolü
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")

if __name__ == '__main__':
    init_db()
