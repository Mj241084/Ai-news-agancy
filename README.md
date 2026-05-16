# Django News Platform

A sophisticated, production-ready Django news and content management system featuring advanced personalization, SEO optimization, real-time interactions, and intelligent content moderation.

## 🎯 Project Overview

This is a comprehensive news platform built with Django that demonstrates modern web application architecture, best practices, and scalable design patterns. The platform supports multi-source content aggregation, user personalization, AI-powered content moderation, and sophisticated analytics.

## ✨ Key Features

### Content Management
- **Multi-source content aggregation** - Manage articles from multiple editorial sources
- **Content versioning** - Track and manage content revisions
- **Rich text editing** - CKEditor integration for comprehensive content creation
- **Media management** - Upload and manage images and media files with Cloudinary integration

### User Experience
- **Personalized feeds** - ML-based content recommendations for each user
- **Smart categorization** - Taxonomy system with hierarchical organization
- **Entity recognition** - Extract and link entities (people, places, organizations)
- **Related content** - Intelligent content relationship system

### Search & Discovery
- **Full-text search** - Fast and accurate content search
- **Advanced filtering** - Filter by categories, entities, date ranges
- **SEO optimization** - Sitemap generation, structured data, schema markup
- **URL slugification** - Clean, SEO-friendly URLs

### Content Moderation & Quality
- **Automated moderation** - Content filtering and spam detection
- **User interactions** - Comments, ratings, engagement tracking
- **Visitor analytics** - Track visitor behavior and engagement metrics
- **OTP-based authentication** - Secure user verification system

### Performance & Scalability
- **Caching strategy** - Redis-ready caching for high traffic
- **Static file optimization** - WhiteNoise for efficient static file serving
- **Query optimization** - Indexed database queries
- **Async support** - ASGI configuration for real-time features

### Integrations
- **Firebase** - Real-time notifications and Firestore database support
- **Google Cloud** - Storage and media hosting
- **SMS notifications** - Kavenegar SMS gateway integration
- **Push notifications** - FCM Django for mobile push notifications

## 📁 Project Structure

```
Django-News-Platform/
├── apps/                          # Django applications
│   ├── accounts/                  # User authentication & management
│   ├── content/                   # Core content management
│   ├── taxonomy/                  # Categories and tags
│   ├── entities/                  # Named entity recognition
│   ├── editorial/                 # Editorial workflow
│   ├── search/                    # Search functionality
│   ├── seo/                       # SEO optimization
│   ├── personalization/           # User recommendations
│   ├── relations/                 # Content relationships
│   ├── interactions/              # User interactions
│   ├── staffpanel/                # Admin panel
│   ├── core/                      # Core utilities
│   └── [other apps]
├── config/                        # Django settings
│   ├── settings.py               # Main settings
│   ├── urls.py                   # URL routing
│   ├── wsgi.py                   # WSGI config
│   └── asgi.py                   # ASGI config
├── templates/                     # HTML templates
├── static/                        # Static files (CSS, JS, images)
├── utils/                         # Utility functions
├── manage.py                      # Django CLI
└── requirements.txt               # Python dependencies
```

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- pip and virtualenv
- PostgreSQL (recommended for production)
- Redis (optional, for caching)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Mj241084/Ai-news-agancy.git
   cd django-news-platform
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   # Copy example environment file
   cp .env.example .env
   
   # Edit .env with your configuration
   # Generate a secure SECRET_KEY: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

5. **Apply database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Collect static files**
   ```bash
   python manage.py collectstatic --noinput
   ```

8. **Run development server**
   ```bash
   python manage.py runserver
   ```

   Visit `http://localhost:8000` in your browser.

## ⚙️ Configuration

### Environment Variables

Key environment variables (see `.env.example` for complete list):

```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database (Development uses SQLite, production uses PostgreSQL)
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=news_db
DATABASE_USER=postgres
DATABASE_PASSWORD=password
DATABASE_HOST=localhost

# Email (for OTP and notifications)
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
SMTP_SERVER=smtp.gmail.com

# OTP Settings
OTP_VALIDITY_SECONDS=300
OTP_MAX_ATTEMPTS=5
```

### Database Configuration

**Development:**
- Uses SQLite by default
- Located at `db.sqlite3`

**Production:**
- Recommended: PostgreSQL
- Update `settings.py` DATABASE configuration or use environment variables

### Caching

For optimal performance in production, configure Redis:

```env
CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
CACHE_LOCATION=redis://127.0.0.1:6379/1
```

## 🏗️ Architecture Highlights

### Apps Responsibility

- **accounts**: User registration, authentication (OTP-based), profile management
- **content**: Article creation, publishing, versioning, rich content editing
- **taxonomy**: Hierarchical categories and tagging system
- **search**: Full-text search with advanced filtering
- **seo**: Sitemap generation, schema markup, meta tags, SEO optimization
- **personalization**: User preferences, reading history, recommendations
- **relations**: Content-to-content relationships and recommendations
- **interactions**: Comments, ratings, user engagement tracking
- **staffpanel**: Administrative dashboard for content management
- **entities**: Entity extraction and linking (persons, places, organizations)

### Key Design Patterns

1. **Service Layer Pattern** - Business logic separated in `services.py`
2. **Signal Handlers** - Cache invalidation and event handling via Django signals
3. **Model Managers** - Custom querysets for optimized data access
4. **Middleware** - Custom middleware for visitor tracking
5. **Management Commands** - Bulk operations and maintenance tasks

## 📊 Database Schema Highlights

- **Content relationships** - N-to-M relationships for related articles
- **User interactions** - Ratings, comments, read tracking
- **Personalization data** - User preferences, reading history
- **Search indexing** - Indexed fields for fast search queries
- **Cache keys** - Structured cache invalidation strategy

## 🔒 Security Features

- **OTP-based authentication** - Secure user verification
- **CSRF protection** - Django's built-in CSRF middleware
- **XFrame options** - Clickjacking protection
- **Environment variables** - No hardcoded secrets
- **SQL injection prevention** - Django ORM protection
- **Content moderation** - Automated spam and abuse detection

## 📈 Performance Optimization

- **Database indexing** - Strategic indexes on frequently queried fields
- **Query optimization** - `select_related()` and `prefetch_related()` usage
- **Caching layers** - Cache invalidation strategies for different content types
- **Static file optimization** - WhiteNoise for CDN-like performance
- **Pagination** - Efficient pagination for large datasets

## 🧪 Testing

Run tests with:
```bash
python manage.py test
# or
pytest
```

## 📦 Deployment

### Using Gunicorn (Production)

```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### Environment Setup for Production

```bash
export DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
export DJANGO_DEBUG=0
export DATABASE_ENGINE=django.db.backends.postgresql
export DATABASE_NAME=news_db
# ... set other environment variables
```

## 🛠️ Development Guidelines

### Code Style
- Follow PEP 8
- Use type hints where applicable
- Write docstrings for classes and functions

### Database Migrations
```bash
# Create migration
python manage.py makemigrations

# Apply migrations
python manage.py migrate
```

### Adding New Apps
```bash
python manage.py startapp new_app_name apps
```

## 📚 Technologies Used

- **Backend**: Django 5.2.7, Django REST Framework
- **Database**: PostgreSQL, MySQL, SQLite
- **Caching**: Redis-ready
- **Authentication**: JWT, OTP
- **Search**: Full-text search
- **Media**: Cloudinary, Google Cloud Storage
- **Notifications**: Firebase, FCM, SMS (Kavenegar)
- **Monitoring**: OpenTelemetry

## 📄 License

MIT License - Feel free to use this project as a learning resource or starting template.

## 🤝 Contributing

Contributions are welcome! Please:
1. Create a feature branch
2. Make your changes
3. Write tests
4. Submit a pull request

## 📞 Support

For issues, questions, or suggestions, please create an GitHub issue.

---

**Built with ❤️ using Django**

Last Updated: May 2026

---

# 🇮🇷 نسخه فارسی

# پلتفرم خبری Django

یک سیستم مدیریت محتوا و خبری Django با قابلیت شخصی‌سازی پیشرفته، بهینه‌سازی SEO، تعاملات بلادرنگ و مدیریت محتوای هوشمند.

## 🎯 مرور کلی پروژه

این یک پلتفرم خبری جامع است که با Django ساخته شده‌است و معماری وب‌ اپلیکیشن مدرن، بهترین شیوه‌ها و الگوهای طراحی مقیاس‌پذیر را نشان می‌دهد. این پلتفرم از جمع‌آوری محتوا از منابع متعدد، شخصی‌سازی کاربر، مدیریت محتوای توسط AI و تحلیلات پیشرفته پشتیبانی می‌کند.

## ✨ ویژگیهای کلیدی

### مدیریت محتوا
- **جمع‌آوری محتوا از منابع متعدد** - مدیریت مقالات از چند منبع تحریری
- **نسخه‌سازی محتوا** - ردیابی و مدیریت تجدیدنظرهای محتوا
- **ویرایش متن غنی** - ادغام CKEditor برای ایجاد محتوای جامع
- **مدیریت رسانه** - بارگذاری و مدیریت تصاویر و فایلهای رسانه‌ای با Cloudinary

### تجربه کاربر
- **خوراک شخصی‌شده** - توصیات محتوا مبتنی بر ML برای هر کاربر
- **دسته‌بندی هوشمند** - سیستم تاکسونومی با سازمان سلسله‌مراتبی
- **تشخیص موجودیت** - استخراج و پیوند موجودیت‌ها (افراد، مکان‌ها، سازمان‌ها)
- **محتوای مرتبط** - سیستم روابط محتوا هوشمند

### جستجو و کشف
- **جستجوی متن کامل** - جستجو سریع و دقیق محتوا
- **فیلترهای پیشرفته** - فیلترکردن بر اساس دسته‌بندی، موجودیت‌ها، بازه‌های زمانی
- **بهینه‌سازی SEO** - تولید نقشه‌سایت، داده‌های ساختارمند، markup schema
- **URL slug** - URL‌های پاک و مناسب برای SEO

### مدیریت و کیفیت محتوا
- **مدیریت خودکار** - فیلترکردن محتوا و تشخیص اسپم
- **تعاملات کاربر** - نظرات، امتیازات، ردیابی تعامل
- **تحلیلات بازدیدکنندگان** - ردیابی رفتار و تعامل بازدیدکنندگان
- **احراز هویت مبتنی بر OTP** - سیستم تایید ایمن کاربر

### عملکرد و مقیاس‌پذیری
- **استراتژی کش** - کش آماده برای ترافیک بالا با Redis
- **بهینه‌سازی فایل‌های ایستا** - WhiteNoise برای عملکرد شبیه CDN
- **بهینه‌سازی پرس‌و‌جو** - کوئری‌های پایگاه‌داده با ایندکس
- **پشتیبانی Async** - پیکربندی ASGI برای ویژگیهای بلادرنگ

### ادغام‌ها
- **Firebase** - اعلان‌های بلادرنگ و پشتیبانی Firestore
- **Google Cloud** - ذخیره‌سازی و میزبانی رسانه
- **اعلان‌های SMS** - درگاه SMS Kavenegar
- **اعلان‌های Push** - FCM Django برای اعلان‌های موبایل

## 📁 ساختار پروژه

```
Django-News-Platform/
├── apps/                          # اپلیکیشن‌های Django
│   ├── accounts/                  # احراز هویت و مدیریت کاربر
│   ├── content/                   # مدیریت محتوای اصلی
│   ├── taxonomy/                  # دسته‌بندی‌ها و برچسب‌ها
│   ├── entities/                  # تشخیص موجودیت نام‌دار
│   ├── editorial/                 # گردش کار تحریری
│   ├── search/                    # عملکرد جستجو
│   ├── seo/                       # بهینه‌سازی SEO
│   ├── personalization/           # توصیات کاربر
│   ├── relations/                 # روابط محتوا
│   ├── interactions/              # تعاملات کاربر
│   ├── staffpanel/                # پنل مدیریت
│   ├── core/                      # ابزارهای اساسی
│   └── [سایر اپلیکیشن‌ها]
├── config/                        # تنظیمات Django
│   ├── settings.py               # تنظیمات اصلی
│   ├── urls.py                   # مسیریابی URL
│   ├── wsgi.py                   # پیکربندی WSGI
│   └── asgi.py                   # پیکربندی ASGI
├── templates/                     # قالب‌های HTML
├── static/                        # فایلهای ایستا (CSS, JS, تصاویر)
├── utils/                         # توابع کمکی
├── manage.py                      # CLI Django
└── requirements.txt               # وابستگی‌های Python
```

## 🚀 شروع کار

### پیش‌نیازها
- Python 3.8+
- pip و virtualenv
- PostgreSQL (برای تولید توصیه می‌شود)
- Redis (اختیاری، برای کش)

### نصب و راه‌اندازی

1. **مخزن را کلون کنید**
   ```bash
   git clone https://github.com/yourusername/django-news-platform.git
   cd django-news-platform
   ```

2. **محیط مجازی را ایجاد کنید**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **وابستگی‌ها را نصب کنید**
   ```bash
   pip install -r requirements.txt
   ```

4. **متغیرهای محیط را پیکربندی کنید**
   ```bash
   # فایل نمونه محیط را کپی کنید
   cp .env.example .env
   
   # .env را با تنظیمات خود ویرایش کنید
   # Generate a secure SECRET_KEY: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

5. **migration‌های پایگاه‌داده را اعمال کنید**
   ```bash
   python manage.py migrate
   ```

6. **کاربر سوپر را ایجاد کنید**
   ```bash
   python manage.py createsuperuser
   ```

7. **فایلهای ایستا را جمع‌آوری کنید**
   ```bash
   python manage.py collectstatic --noinput
   ```

8. **سرور توسعه را اجرا کنید**
   ```bash
   python manage.py runserver
   ```

   `http://localhost:8000` را در مرورگر خود بازدید کنید.

## ⚙️ پیکربندی

### متغیرهای محیط

متغیرهای محیط کلیدی (برای لیست کامل `.env.example` را ببینید):

```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database (توسعه از SQLite، تولید از PostgreSQL استفاده می‌کند)
DATABASE_ENGINE=django.db.backends.postgresql
DATABASE_NAME=news_db
DATABASE_USER=postgres
DATABASE_PASSWORD=password
DATABASE_HOST=localhost

# Email (برای OTP و اعلان‌ها)
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
SMTP_SERVER=smtp.gmail.com

# OTP Settings
OTP_VALIDITY_SECONDS=300
OTP_MAX_ATTEMPTS=5
```

### پیکربندی پایگاه‌داده

**توسعه:**
- به‌طور پیش‌فرض از SQLite استفاده می‌کند
- در `db.sqlite3` قرار دارد

**تولید:**
- توصیه شده: PostgreSQL
- پیکربندی DATABASE در `settings.py` یا استفاده از متغیرهای محیط را به‌روزرسانی کنید

### کش

برای عملکرد بهینه در تولید، Redis را پیکربندی کنید:

```env
CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
CACHE_LOCATION=redis://127.0.0.1:6379/1
```

## 🏗️ نکات معماری

### مسئولیت اپلیکیشن‌ها

- **accounts**: ثبت‌نام کاربر، احراز هویت (مبتنی بر OTP)، مدیریت پروفایل
- **content**: ایجاد مقاله، انتشار، نسخه‌سازی، ویرایش محتوای غنی
- **taxonomy**: سیستم دسته‌بندی و برچسپ‌گذاری سلسله‌مراتبی
- **search**: جستجوی متن کامل با فیلترهای پیشرفته
- **seo**: تولید نقشه‌سایت، markup schema، meta tag، بهینه‌سازی SEO
- **personalization**: ترجیحات کاربر، سابقه مطالعه، توصیات
- **relations**: روابط محتوا و توصیات محتوا
- **interactions**: نظرات، امتیازات، ردیابی تعامل کاربر
- **staffpanel**: پنل مدیریت برای مدیریت محتوا
- **entities**: استخراج و پیوند موجودیت‌ها (افراد، مکان‌ها، سازمان‌ها)

### الگوهای طراحی کلیدی

1. **الگوی Service Layer** - منطق کسب‌وکار در `services.py` جدا شده
2. **Signal Handlers** - باطل کردن کش و مدیریت رویداد از طریق signal‌های Django
3. **Model Managers** - querysets سفارشی برای دسترسی بهینه به داده
4. **Middleware** - middleware سفارشی برای ردیابی بازدیدکننده
5. **Management Commands** - عملیات دسته‌ای و وظایف نگهداری

## 📊 نکات طراحی پایگاه‌داده

- **روابط محتوا** - روابط N-to-M برای مقالات مرتبط
- **تعاملات کاربر** - امتیازات، نظرات، ردیابی خواندن
- **داده‌های شخصی‌سازی** - ترجیحات کاربر، سابقه مطالعه
- **ایندکس‌های جستجو** - فیلدهای ایندکس‌شده برای جستجوی سریع
- **کلیدهای کش** - استراتژی ساختار‌یافته برای باطل کردن کش

## 🔒 ویژگیهای امنیتی

- **احراز هویت مبتنی بر OTP** - تایید ایمن کاربر
- **حفاظت CSRF** - middleware CSRF داخلی Django
- **گزینه‌های XFrame** - حفاظت از Clickjacking
- **متغیرهای محیط** - بدون رازهای کدشده
- **جلوگیری از SQL injection** - حفاظت ORM Django
- **مدیریت محتوا** - فیلترکردن خودکار اسپم و سوء استفاده

## 📈 بهینه‌سازی عملکرد

- **ایندکس‌سازی پایگاه‌داده** - ایندکس‌های استراتژیک برای فیلدهای پرس‌و‌جو شده
- **بهینه‌سازی پرس‌و‌جو** - استفاده از `select_related()` و `prefetch_related()`
- **لایه‌های کش** - استراتژی‌های باطل کردن کش برای انواع محتوای مختلف
- **بهینه‌سازی فایل‌های ایستا** - WhiteNoise برای عملکرد شبیه CDN
- **صفحه‌بندی** - صفحه‌بندی کارآمد برای مجموعه‌های بزرگ

## 🧪 تست

تست‌ها را با این دستور اجرا کنید:
```bash
python manage.py test
# یا
pytest
```

## 📦 استقرار

### استفاده از Gunicorn (تولید)

```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### تنظیم محیط برای تولید

```bash
export DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
export DJANGO_DEBUG=0
export DATABASE_ENGINE=django.db.backends.postgresql
export DATABASE_NAME=news_db
# ... متغیرهای محیط دیگر را تعیین کنید
```

## 🛠️ راهنمایی توسعه

### سبک کد
- PEP 8 را دنبال کنید
- در مواقع مناسب type hints استفاده کنید
- برای کلاس‌ها و توابع docstring بنویسید

### migration‌های پایگاه‌داده
```bash
# ایجاد migration
python manage.py makemigrations

# اعمال migration‌ها
python manage.py migrate
```

### افزودن اپلیکیشن جدید
```bash
python manage.py startapp new_app_name apps
```

## 📚 تکنولوژی‌های استفاده شده

- **Backend**: Django 5.2.7، Django REST Framework
- **پایگاه‌داده**: PostgreSQL، MySQL، SQLite
- **کش**: آماده برای Redis
- **احراز هویت**: JWT، OTP
- **جستجو**: جستجوی متن کامل
- **رسانه**: Cloudinary، Google Cloud Storage
- **اعلان‌ها**: Firebase، FCM، SMS (Kavenegar)
- **نظارت**: OpenTelemetry

## 📄 مجوز

MIT License - این پروژه را می‌توانید به‌عنوان منبع یادگیری یا قالب شروع استفاده کنید.

## 🤝 مشارکت

مشارکت‌ها خوش‌آمد! لطفاً:
1. شاخه ویژگی ایجاد کنید
2. تغییرات خود را انجام دهید
3. تست‌ها بنویسید
4. Pull Request ارسال کنید

## 📞 پشتیبانی

برای مشکلات، سؤالات یا پیشنهادات، لطفاً GitHub issue ایجاد کنید.

---

**با ❤️ و با استفاده از Django ساخته شده**

آخرین به‌روزرسانی: آوریل 2026
