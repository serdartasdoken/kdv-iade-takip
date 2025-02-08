from app import app, db, User

with app.app_context():
    admin = User(username='admin', is_admin=True)
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()
    print("Admin kullanıcısı oluşturuldu!")
