from app import app, db, DosyaHareket, get_tr_time

with app.app_context():
    # İlk dosya için test hareketi oluştur
    hareket = DosyaHareket(
        dosya_id=1,
        islem='Test işlemi',
        aciklama='Test açıklaması',
        user_id=1
    )
    db.session.add(hareket)
    db.session.commit()
    print('Test hareket oluşturuldu')
