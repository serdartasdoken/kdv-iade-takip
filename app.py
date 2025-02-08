from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from datetime import timedelta
from sqlalchemy import inspect, text, func, extract
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from config import Config
import boto3
from botocore.exceptions import ClientError

def get_tr_time():
    return datetime.utcnow() + timedelta(hours=3)

app = Flask(__name__)
app.config.from_object(Config)

# Set upload folder path
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Upload klasörünü oluştur
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    dosyalar = db.relationship('Dosya', backref='user', lazy=True, foreign_keys='Dosya.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

DURUM_SECENEKLERI = [
    'Mahsuben iade',
    'İade listeleri geldi',
    'Rapor hazırlanacak',
    'Rapor yazıldı',
    'Rapor yazılıyor',
    'Eksiklik yazısı cevap',
    'Eksiklik yazısı',
    'Vergi İnceleme'
]

class EksiklikYazisi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dosya_id = db.Column(db.Integer, db.ForeignKey('dosya.id'), nullable=False)
    dosya_adi = db.Column(db.String(255), nullable=False)
    yuklenme_tarihi = db.Column(db.DateTime, nullable=False, default=get_tr_time)
    cevaplandirma_tarihi = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='eksiklik_yazilari', lazy=True)

class Dosya(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(200), nullable=False)
    vergi_no = db.Column(db.String(10), nullable=False)
    donem = db.Column(db.String(7), nullable=False)  # YYYY/MM formatında
    iade_turu = db.Column(db.String(50), nullable=False)
    iade_tutari = db.Column(db.Float, nullable=False)
    durum = db.Column(db.String(50), nullable=False)
    acilis_tarihi = db.Column(db.DateTime, nullable=False, default=get_tr_time)
    son_islem_tarihi = db.Column(db.DateTime, nullable=False, default=get_tr_time)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notlar = db.Column(db.Text)
    arsivde = db.Column(db.Boolean, default=False)  # Arşiv durumu
    hareketler = db.relationship('DosyaHareket', backref='dosya', lazy=True)
    kontrol_raporlari = db.relationship('KontrolRaporu', backref='dosya', lazy=True)
    eksiklik_yazilari = db.relationship('EksiklikYazisi', backref='dosya', lazy=True)
    karsitlar = db.relationship('Karsit', backref='dosya', lazy=True)
    
    # Süreç tarihleri
    kayit_tarihi = db.Column(db.DateTime)  # Listelerin Geliş Tarihi
    karsit_liste_tarihi = db.Column(db.DateTime)  # Karşıt Listesi Hazırlama Tarihi
    rapor_teslim_tarihi = db.Column(db.DateTime)  # Rapor Teslim/Mahsup Liste Giriş Tarihi
    iade_talep_tarihi = db.Column(db.DateTime)  # İade Talep Dilekçesi Giriş Tarihi
    rapor_ekleri_tarihi = db.Column(db.DateTime)  # Rapor Ekleri Teslim Tarihi
    

    
    # Yeni alanlar ekleyelim
    makbuz_tarihi = db.Column(db.DateTime)
    makbuz_no = db.Column(db.String(50))
    
    # Yeni onay durumu alanları
    iade_listesi_onay = db.Column(db.Boolean, default=False)
    rapor_onay = db.Column(db.Boolean, default=False)
    
    # Yeni alanlar
    teminat_mektubu = db.Column(db.Boolean, default=False)
    on_kontrol_talebi = db.Column(db.Boolean, default=False)
    iade_sekli = db.Column(db.String(50), nullable=True)
    
    def hesapla_sureler(self):
        # Rapor Hazırlama Süresi hesaplama
        self.rapor_hazirlama_suresi = None
        if self.rapor_teslim_tarihi and self.acilis_tarihi:
            self.rapor_hazirlama_suresi = (self.rapor_teslim_tarihi - self.acilis_tarihi).days
        return self
        """Çeşitli süreleri hesaplar"""
        bugun = datetime.now().date()
        sureler = {}
        
        # Rapor süreleri
        if self.rapor_teslim_tarihi:
            sureler['rapor_teslim_kalan'] = (self.rapor_teslim_tarihi.date() - bugun).days
            if self.kayit_tarihi:
                sureler['rapor_hazirlama_sure'] = (self.rapor_teslim_tarihi.date() - self.kayit_tarihi.date()).days
        
        return sureler

class DosyaHareket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dosya_id = db.Column(db.Integer, db.ForeignKey('dosya.id'), nullable=False)
    islem_tarihi = db.Column(db.DateTime, nullable=False, default=get_tr_time)
    islem = db.Column(db.String(200), nullable=False)
    aciklama = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='hareketler', lazy=True)

class Karsit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dosya_id = db.Column(db.Integer, db.ForeignKey('dosya.id'), nullable=False)
    kayit_acilis_tarihi = db.Column(db.DateTime, nullable=False, default=get_tr_time)
    alt_firma_sirasi = db.Column(db.Integer, nullable=False)  # 1 veya 2
    alt_firma_unvani = db.Column(db.String(200), nullable=False)
    telefon = db.Column(db.String(20))
    email = db.Column(db.String(100))
    ilgili_kisi = db.Column(db.String(100))
    aciklama = db.Column(db.Text)
    karsit_durumu = db.Column(db.String(20), nullable=False, default='Gelmedi')  # 'Geldi' veya 'Gelmedi'
    sonraki_karsit_dikkat = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='karsitlar', lazy=True)

class KontrolRaporu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dosya_id = db.Column(db.Integer, db.ForeignKey('dosya.id'), nullable=False)

    dosya_adi = db.Column(db.String(255), nullable=False)
    yuklenme_tarihi = db.Column(db.DateTime, nullable=False, default=get_tr_time)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='kontrol_raporlari', lazy=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def calculate_monthly_stats(year, month):
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    # SQLite için julianday fonksiyonu yerine SQLAlchemy'nin datetime işlemlerini kullanalım
    stats = {
        'toplam_iade': db.session.query(func.sum(Dosya.iade_tutari)).filter(
            Dosya.acilis_tarihi >= start_date,
            Dosya.acilis_tarihi < end_date
        ).scalar() or 0,
        'dosya_sayisi': db.session.query(Dosya).filter(
            Dosya.acilis_tarihi >= start_date,
            Dosya.acilis_tarihi < end_date
        ).count(),
        'ortalama_sure': db.session.query(
            func.avg(
                func.extract('epoch', Dosya.son_islem_tarihi - Dosya.acilis_tarihi) / 86400
            )
        ).filter(
            Dosya.acilis_tarihi >= start_date,
            Dosya.acilis_tarihi < end_date
        ).scalar() or 0
    }
    return stats

def calculate_yearly_stats(year):
    stats = {
        'aylik_istatistikler': [],
        'toplam_iade': 0,
        'toplam_dosya': 0,
        'ortalama_sure': 0
    }
    
    for month in range(1, 13):
        aylik_stat = calculate_monthly_stats(year, month)
        stats['aylik_istatistikler'].append({
            'ay': month,
            'iade_tutari': aylik_stat['toplam_iade'],
            'dosya_sayisi': aylik_stat['dosya_sayisi'],
            'ortalama_sure': aylik_stat['ortalama_sure']
        })
        stats['toplam_iade'] += aylik_stat['toplam_iade']
        stats['toplam_dosya'] += aylik_stat['dosya_sayisi']
        if aylik_stat['ortalama_sure']:
            stats['ortalama_sure'] += aylik_stat['ortalama_sure']
    
    if stats['toplam_dosya'] > 0:
        stats['ortalama_sure'] /= 12
    
    return stats

def calculate_company_performance(firma_vergi_no):
    dosyalar = Dosya.query.filter_by(vergi_no=firma_vergi_no).all()
    if not dosyalar:
        return None
    
    performance = {
        'toplam_dosya': len(dosyalar),
        'toplam_iade': sum(d.iade_tutari for d in dosyalar),
        'ortalama_sure': 0,
        'durum_dagilimi': defaultdict(int),
        'son_islemler': []
    }
    
    toplam_sure = 0
    for dosya in dosyalar:
        sure = (dosya.son_islem_tarihi - dosya.acilis_tarihi).days
        toplam_sure += sure
        performance['durum_dagilimi'][dosya.durum] += 1
        
        son_hareket = DosyaHareket.query.filter_by(dosya_id=dosya.id).order_by(DosyaHareket.islem_tarihi.desc()).first()
        if son_hareket:
            performance['son_islemler'].append({
                'dosya_id': dosya.id,
                'islem': son_hareket.islem,
                'tarih': son_hareket.islem_tarihi
            })
    
    performance['ortalama_sure'] = toplam_sure / len(dosyalar)
    return performance

@app.route('/dashboard')
@login_required
def dashboard():
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Yıllık istatistikler
    yearly_stats = calculate_yearly_stats(current_year)
    
    # Aylık istatistikler
    monthly_stats = calculate_monthly_stats(current_year, current_month)
    
    # En yüksek iade tutarlı firmalar
    top_companies = db.session.query(
        Dosya.vergi_no,
        Dosya.firma_adi,
        func.sum(Dosya.iade_tutari).label('toplam_iade')
    ).group_by(Dosya.vergi_no).order_by(text('toplam_iade DESC')).limit(5).all()
    
    return render_template('dashboard.html',
                           yearly_stats=yearly_stats,
                           monthly_stats=monthly_stats,
                           top_companies=top_companies)

@app.route('/firma_performans/<vergi_no>')
@login_required
def firma_performans(vergi_no):
    performance = calculate_company_performance(vergi_no)
    if not performance:
        flash('Firma bulunamadı')
        return redirect(url_for('dashboard'))
    
    return render_template('firma_performans.html', performance=performance)

@app.route('/')
@login_required
def index():
    arsivde = request.args.get('arsivde', 'false') == 'true'
    # Tüm kullanıcılar tüm dosyaları görebilir
    dosyalar = Dosya.query.filter_by(arsivde=arsivde).all()
    
    # Tüm dosyalar için süreleri hesapla
    for dosya in dosyalar:
        dosya.hesapla_sureler()
    
    return render_template('index.html', dosyalar=dosyalar, arsivde=arsivde)

@app.route('/dosya/arsivle/<int:id>', methods=['GET', 'POST'])
@login_required
def dosya_arsivle(id):
    dosya = Dosya.query.get_or_404(id)
    
    # Sadece admin arşivleyebilir
    if not current_user.is_admin:
        flash('Dosyaları arşive kaldırma yetkisine sahip değilsiniz')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        makbuz_tarihi = request.form.get('makbuz_tarihi')
        makbuz_no = request.form.get('makbuz_no')
        
        if not makbuz_tarihi or not makbuz_no:
            flash('Makbuz tarih ve numarası zorunludur')
            return redirect(url_for('dosya_detay', id=id))
            
        dosya.makbuz_tarihi = datetime.strptime(makbuz_tarihi, '%Y-%m-%d')
        dosya.makbuz_no = makbuz_no
        dosya.arsivde = True
        
        hareket = DosyaHareket(
            dosya_id=dosya.id,
            islem=f'Dosya arşivlendi (Makbuz No: {makbuz_no})',
            user_id=current_user.id
        )
        db.session.add(hareket)
        db.session.commit()
        
        flash('Dosya arşive kaldırıldı')
        return redirect(url_for('index'))
        
    return render_template('arsivle.html', dosya=dosya)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Geçersiz kullanıcı adı veya şifre')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dosya/yeni', methods=['GET', 'POST'])
@login_required
def yeni_dosya():
    if request.method == 'POST':
        dosya = Dosya(
            firma_adi=request.form['firma_adi'],
            vergi_no=request.form['vergi_no'],
            donem=request.form['donem'],
            iade_turu=request.form['iade_turu'],
            iade_tutari=float(request.form['iade_tutari']),
            iade_sekli=request.form['iade_sekli'],
            teminat_mektubu=request.form.get('teminat_mektubu') == 'true',
            on_kontrol_talebi=request.form.get('on_kontrol_talebi') == 'true',
            user_id=current_user.id,
            durum='İade listeleri geldi'  # Varsayılan durum
        )
        db.session.add(dosya)
        db.session.commit()
        
        hareket = DosyaHareket(
            dosya_id=dosya.id,
            islem='Dosya açıldı',
            user_id=current_user.id
        )
        db.session.add(hareket)
        db.session.commit()
        
        return redirect(url_for('index'))
    return render_template('yeni_dosya.html')

@app.route('/dosya/<int:id>', methods=['GET', 'POST'])
@login_required
def dosya_detay(id):
    dosya = Dosya.query.get_or_404(id)
    # Tüm kullanıcılar tüm dosyaların detaylarını görebilir
    
    if request.method == 'POST':
        if 'durum' in request.form:
            yeni_durum = request.form.get('durum')
            aciklama = request.form.get('aciklama', '')
            if yeni_durum in DURUM_SECENEKLERI:
                eski_durum = dosya.durum
                dosya.durum = yeni_durum
                dosya.son_islem_tarihi = get_tr_time()
                
                hareket = DosyaHareket(
                    dosya_id=dosya.id,
                    islem=f'Durum değiştirildi: {eski_durum} -> {yeni_durum}',
                    aciklama=aciklama,
                    user_id=current_user.id
                )
                db.session.add(hareket)
                db.session.commit()
                flash('Dosya durumu güncellendi')
                return redirect(url_for('dosya_detay', id=id))
        
        elif 'kontrol_raporu' in request.files:
            rapor = request.files['kontrol_raporu']
            if rapor.filename != '':
                filename = secure_filename(rapor.filename)
                # Dosyayı yerel sisteme kaydet
                filename = secure_filename(rapor.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'kontrol_raporlari', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                rapor.save(filepath)
                
                kontrol_raporu = KontrolRaporu(
                    dosya_id=dosya.id,
                    dosya_adi=filename,
                    user_id=current_user.id
                )
                db.session.add(kontrol_raporu)
                db.session.commit()
                flash('Kontrol raporu yüklendi')
                return redirect(url_for('dosya_detay', id=id))
        
        elif 'eksiklik_yazisi' in request.files:
            yazisi = request.files['eksiklik_yazisi']
            if yazisi.filename != '':
                filename = secure_filename(yazisi.filename)
                # Dosyayı yerel sisteme kaydet
                filename = secure_filename(yazisi.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'eksiklik_yazilari', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                yazisi.save(filepath)
                
                eksiklik = EksiklikYazisi(
                    dosya_id=dosya.id,
                    dosya_adi=filename,
                    user_id=current_user.id
                )
                db.session.add(eksiklik)
                db.session.commit()
                flash('Eksiklik yazısı yüklendi')
                return redirect(url_for('dosya_detay', id=id))
        
        # Tarih güncellemeleri
        tarih_alanlari = [
            'karsit_liste_tarihi', 'rapor_teslim_tarihi',
            'iade_talep_tarihi', 'rapor_ekleri_tarihi'
        ]
        
        guncellenen_tarihler = []
        for alan in tarih_alanlari:
            tarih_str = request.form.get(alan)
            if tarih_str:
                try:
                    yeni_tarih = datetime.strptime(tarih_str, '%Y-%m-%d').date()
                    eski_tarih = getattr(dosya, alan)
                    if not eski_tarih or eski_tarih.date() != yeni_tarih:
                        setattr(dosya, alan, yeni_tarih)
                        guncellenen_tarihler.append(alan)
                except ValueError:
                    pass
        
        if guncellenen_tarihler:
            hareket = DosyaHareket(
                dosya_id=dosya.id,
                islem=f'Tarihler güncellendi: {", ".join(guncellenen_tarihler)}',
                user_id=current_user.id
            )
            db.session.add(hareket)
            db.session.commit()
            flash('Tarihler güncellendi')
            return redirect(url_for('dosya_detay', id=id))
        
        # Onay durumlarını güncelle
        iade_listesi_onay = request.form.get('iade_listesi_onay') == 'true'
        rapor_onay = request.form.get('rapor_onay') == 'true'
        
        if iade_listesi_onay != dosya.iade_listesi_onay or rapor_onay != dosya.rapor_onay:
            dosya.iade_listesi_onay = iade_listesi_onay
            dosya.rapor_onay = rapor_onay
            dosya.son_islem_tarihi = get_tr_time()
            
            hareket = DosyaHareket(
                dosya_id=dosya.id,
                islem='Onay durumları güncellendi',
                user_id=current_user.id
            )
            db.session.add(hareket)
            db.session.commit()
            flash('Onay durumları güncellendi')
            
        return redirect(url_for('dosya_detay', id=id))
    
    hareketler = DosyaHareket.query.filter_by(dosya_id=id).order_by(DosyaHareket.islem_tarihi.desc()).all()
    kontrol_raporlari = KontrolRaporu.query.filter_by(dosya_id=id).order_by(KontrolRaporu.yuklenme_tarihi.desc()).all()
    return render_template('dosya_detay.html', dosya=dosya, hareketler=hareketler, 
                         durum_secenekleri=DURUM_SECENEKLERI, kontrol_raporlari=kontrol_raporlari,
                         now=get_tr_time())

@app.route('/kontrol-raporu/<int:id>')
@login_required
def kontrol_raporu_indir(id):
    rapor = KontrolRaporu.query.get_or_404(id)
    if not current_user.is_admin and rapor.dosya.user_id != current_user.id:
        flash('Bu rapora erişim yetkiniz yok')
        return redirect(url_for('index'))
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'kontrol_raporlari', rapor.dosya_adi)
    return send_file(
        filepath,
        download_name=rapor.dosya_adi,
        as_attachment=True
    )

@app.route('/eksiklik-yazisi/<int:id>')
@login_required
def eksiklik_yazisi_indir(id):
    yazisi = EksiklikYazisi.query.get_or_404(id)
    if not current_user.is_admin and yazisi.dosya.user_id != current_user.id:
        flash('Bu yazıya erişim yetkiniz yok')
        return redirect(url_for('index'))
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'eksiklik_yazilari', yazisi.dosya_adi)
    return send_file(
        filepath,
        download_name=yazisi.dosya_adi,
        as_attachment=True
    )

@app.route('/kullanicilar', methods=['GET', 'POST'])
@login_required
def kullanicilar():
    if not current_user.is_admin:
        flash('Bu sayfaya erişim yetkiniz yok')
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Bu kullanıcı adı zaten kullanılıyor')
        else:
            user = User(username=username, is_admin=False)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Kullanıcı başarıyla oluşturuldu')
            
    users = User.query.all()
    return render_template('kullanicilar.html', users=users)

@app.route('/kullanici_sil/<int:user_id>', methods=['POST'])
@login_required
def kullanici_sil(user_id):
    if not current_user.is_admin:
        flash('Bu işlem için yetkiniz yok')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Admin kullanıcısı silinemez')
        return redirect(url_for('kullanicilar'))
        
    db.session.delete(user)
    db.session.commit()
    flash('Kullanıcı başarıyla silindi')
    return redirect(url_for('kullanicilar'))

@app.route('/eksiklik_yazisi_sil/<int:id>', methods=['POST'])
@login_required
def eksiklik_yazisi_sil(id):
    yazisi = EksiklikYazisi.query.get_or_404(id)
    dosya_id = yazisi.dosya_id
    
    # Dosyayı sil
    dosya_yolu = os.path.join(app.config['UPLOAD_FOLDER'], yazisi.dosya_adi)
    if os.path.exists(dosya_yolu):
        os.remove(dosya_yolu)
    
    # Veritabanı kaydını sil
    db.session.delete(yazisi)
    db.session.commit()
    
    flash('Eksiklik yazısı başarıyla silindi.', 'success')
    return redirect(url_for('dosya_detay', id=dosya_id))

@app.route('/eksiklik_yazisi_cevaplandirma_tarihi/<int:id>', methods=['POST'])
@login_required
def eksiklik_yazisi_cevaplandirma_tarihi(id):
    yazisi = EksiklikYazisi.query.get_or_404(id)
    tarih_str = request.form.get('tarih')
    
    try:
        if tarih_str:
            tarih = datetime.strptime(tarih_str, '%Y-%m-%d')
            yazisi.cevaplandirma_tarihi = tarih
        else:
            yazisi.cevaplandirma_tarihi = None
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/karsit/ekle/<int:dosya_id>', methods=['POST'])
@login_required
def karsit_ekle(dosya_id):
    dosya = Dosya.query.get_or_404(dosya_id)
    
    # Yeni karşıt oluştur
    karsit = Karsit(
        dosya_id=dosya.id,
        alt_firma_sirasi=request.form.get('alt_firma_sirasi', type=int),
        alt_firma_unvani=request.form.get('alt_firma_unvani'),
        telefon=request.form.get('telefon'),
        email=request.form.get('email'),
        ilgili_kisi=request.form.get('ilgili_kisi'),
        aciklama=request.form.get('aciklama'),
        karsit_durumu=request.form.get('karsit_durumu'),
        sonraki_karsit_dikkat=request.form.get('sonraki_karsit_dikkat'),
        user_id=current_user.id
    )
    
    db.session.add(karsit)
    db.session.commit()
    
    # İşlem kaydı ekle
    hareket = DosyaHareket(
        dosya_id=dosya.id,
        islem='Karşıt Eklendi',
        aciklama=f'Karşıt firma eklendi: {karsit.alt_firma_unvani}',
        user_id=current_user.id
    )
    db.session.add(hareket)
    db.session.commit()
    
    flash('Karşıt firma başarıyla eklendi.', 'success')
    return redirect(url_for('dosya_detay', id=dosya.id))

@app.route('/karsit/duzenle/<int:id>', methods=['POST'])
@login_required
def karsit_duzenle(id):
    karsit = Karsit.query.get_or_404(id)
    
    karsit.alt_firma_sirasi = request.form.get('alt_firma_sirasi', type=int)
    karsit.alt_firma_unvani = request.form.get('alt_firma_unvani')
    karsit.telefon = request.form.get('telefon')
    karsit.email = request.form.get('email')
    karsit.ilgili_kisi = request.form.get('ilgili_kisi')
    karsit.aciklama = request.form.get('aciklama')
    karsit.karsit_durumu = request.form.get('karsit_durumu')
    karsit.sonraki_karsit_dikkat = request.form.get('sonraki_karsit_dikkat')
    
    db.session.commit()
    
    # İşlem kaydı ekle
    hareket = DosyaHareket(
        dosya_id=karsit.dosya_id,
        islem='Karşıt Güncellendi',
        aciklama=f'Karşıt firma güncellendi: {karsit.alt_firma_unvani}',
        user_id=current_user.id
    )
    db.session.add(hareket)
    db.session.commit()
    
    flash('Karşıt firma başarıyla güncellendi.', 'success')
    return redirect(url_for('dosya_detay', id=karsit.dosya_id))

@app.route('/karsit/sil/<int:id>', methods=['POST'])
@login_required
def karsit_sil(id):
    karsit = Karsit.query.get_or_404(id)
    dosya_id = karsit.dosya_id
    firma_unvani = karsit.alt_firma_unvani
    
    db.session.delete(karsit)
    
    # İşlem kaydı ekle
    hareket = DosyaHareket(
        dosya_id=dosya_id,
        islem='Karşıt Silindi',
        aciklama=f'Karşıt firma silindi: {firma_unvani}',
        user_id=current_user.id
    )
    db.session.add(hareket)
    db.session.commit()
    
    flash('Karşıt firma başarıyla silindi.', 'success')
    return redirect(url_for('dosya_detay', id=dosya_id))

@app.route('/kontrol-raporu/sil/<int:id>', methods=['POST'])
@login_required
def kontrol_raporu_sil(id):
    rapor = KontrolRaporu.query.get_or_404(id)
    dosya_id = rapor.dosya_id
    
    # Dosyayı sil
    dosya_yolu = os.path.join(app.config['UPLOAD_FOLDER'], rapor.dosya_adi)
    if os.path.exists(dosya_yolu):
        os.remove(dosya_yolu)
    
    # Veritabanından kaydı sil
    db.session.delete(rapor)
    db.session.commit()
    
    flash('Kontrol raporu silindi')
    return redirect(url_for('dosya_detay', id=dosya_id))

def upload_file_to_s3(file, bucket_name, object_name=None):
    if object_name is None:
        object_name = file.filename
        
    s3_client = boto3.client('s3',
        aws_access_key_id=app.config['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=app.config['AWS_SECRET_ACCESS_KEY'],
        region_name=app.config['AWS_REGION']
    )
    try:
        s3_client.upload_fileobj(file, bucket_name, object_name)
        return True
    except ClientError as e:
        print(f"Error uploading file: {e}")
        return False

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Mevcut şifreyi kontrol et
        if not current_user.check_password(current_password):
            flash('Mevcut şifre yanlış!', 'danger')
            return redirect(url_for('change_password'))
        
        # Yeni şifrelerin eşleştiğini kontrol et
        if new_password != confirm_password:
            flash('Yeni şifreler eşleşmiyor!', 'danger')
            return redirect(url_for('change_password'))
        
        # Şifreyi güncelle
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('Şifreniz başarıyla değiştirildi!', 'success')
        return redirect(url_for('index'))
    
    return render_template('change_password.html')

if __name__ == '__main__':
    import os
    
    with app.app_context():
        # Veritabanı tablolarını oluştur
        db.create_all()
        
        # Migrations'ı uygula
        from flask_migrate import upgrade as _upgrade
        _upgrade()
        
        # Admin kullanıcısı kontrolü
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin = User(username='admin', is_admin=True)
            admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
            db.session.add(admin)
            db.session.commit()
    
    # Development sunucusu
    if os.environ.get('FLASK_ENV') == 'development':
        app.run(debug=True, port=5001)
    else:
        app.run()
