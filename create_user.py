from app import db, User

# Veritabanı tablolarını oluştur
db.create_all()

# Yeni kullanıcı oluştur
username = "admin"  # İstediğiniz kullanıcı adını girin
password = "admin123"  # İstediğiniz şifreyi girin

# Kullanıcının daha önce var olup olmadığını kontrol et
existing_user = User.query.filter_by(username=username).first()
if existing_user is None:
    user = User(username=username, is_admin=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Kullanıcı '{username}' başarıyla oluşturuldu!")
else:
    print(f"'{username}' kullanıcısı zaten var!")
