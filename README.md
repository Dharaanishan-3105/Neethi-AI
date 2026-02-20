<div align="center">

# ⚖️ NeethiAI

**Creator: Dharaanishan**

<div align="center">
  <img src="./static/icons/logo.jpg" alt="NeethiAI Logo" width="100" height="100">
</div>

### உங்கள் சட்ட AI உதவியாளர் | Your Legal AI Assistant

**An AI-powered legal assistant for Indian citizens, specializing in Tamil and English legal queries with advanced document analysis and fraud detection capabilities.**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.3+-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

</div>

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [🎯 Project Overview](#-project-overview)
- [🚀 Quick Start](#-quick-start)
- [📦 Installation](#-installation)
- [🌐 Deployment](#-deployment)
- [🏗️ Architecture](#️-architecture)
- [🛠️ Tech Stack](#️-tech-stack)
- [📱 Mobile Support](#-mobile-support)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)
- [🙏 Acknowledgments](#-acknowledgments)

---

## ✨ Features

### 🤖 Core Capabilities

- **🎯 AI-Powered Legal Assistance**
  - Instant legal guidance using NeethiAI
  - Context-aware responses based on Indian legal framework
  - Real-time date/time awareness for current legal information

- **🌐 Bilingual Support**
  - Full Tamil (தமிழ்) and English language support
  - Automatic language detection
  - Explicit language preference override ("in tamil" / "in english")
  - Voice input/output in both languages

- **📄 Document Analysis**
  - Upload PDF, DOCX, and image documents
  - AI-powered summarization and analysis
  - OCR-powered text extraction from images
  - Document context storage for follow-up queries

- **🔍 Fraud Detection**
  - Advanced fake notice detection using OCR
  - Pattern recognition for fraudulent legal documents
  - Real-time analysis with detailed risk assessment

- **🎤 Voice Interaction**
  - Voice input with Web Speech API
  - Text-to-speech in Tamil and English
  - Mobile-optimized voice handling

- **💾 Persistent Storage**
  - PostgreSQL database for chat history
  - Conversation management
  - User profile and statistics
  - Encrypted chat storage support

### 🎨 Modern UI/UX

- **Professional Legal-Tech Design**
  - Dark theme optimized for legal professionals
  - Full-screen immersive chat interface
  - Responsive design for desktop and mobile
  - Glassmorphism effects with subtle animations
  - Accessible and intuitive navigation

- **Progressive Web App (PWA)**
  - Installable on mobile devices
  - Offline capability
  - Custom app icons and branding
  - Native app-like experience

---

## 🎯 Project Overview

**NeethiAI** is a comprehensive legal AI assistant designed specifically for Indian citizens. Built as a final-year project, it combines cutting-edge AI technology with user-friendly design to provide accessible legal guidance.

### Key Highlights

- ✅ **Production-Ready**: Fully deployed and functional
- ✅ **Scalable Architecture**: Built with Flask and PostgreSQL
- ✅ **Modern Stack**: Latest technologies and best practices
- ✅ **Mobile-First**: Responsive design with PWA support
- ✅ **Secure**: User authentication with OAuth integration
- ✅ **Bilingual**: Native Tamil and English support

## 🚀 Quick Start

### Prerequisites

- **Python** 3.8 or higher
- **PostgreSQL** 12 or higher
- **Git** (for cloning)

### One-Command Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/neethiai.git
cd neethiai

# Create virtual environment (Windows)
python -m venv neethi_env
neethi_env\Scripts\activate

# Create virtual environment (Linux/Mac)
python3 -m venv neethi_env
source neethi_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables (see Configuration section)
# Then run the application
python neethi.py
```

Visit `http://localhost:5000` in your browser! 🎉

---

## 📦 Installation

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/neethiai.git
cd neethiai
```

### Step 2: Create Virtual Environment

**Windows:**

```bash
python -m venv neethi_env
neethi_env\Scripts\activate
```

**Linux/Mac:**

```bash
python3 -m venv neethi_env
source neethi_env/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Set Up PostgreSQL Database

```sql
CREATE DATABASE neethi_ai;
CREATE USER neethi_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE neethi_ai TO neethi_user;
```

### Step 5: Configure Environment Variables

Create a `.env` file in the root directory:

```bash
# Required
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://neethi_user:password@localhost:5432/neethi_ai

# Optional - OAuth (for social login)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
LINKEDIN_CLIENT_ID=your-linkedin-client-id
LINKEDIN_CLIENT_SECRET=your-linkedin-client-secret
```

### Step 6: Run the Application

```bash
python neethi.py
```

The application will start on `http://localhost:5000`

---

## 🌐 Deployment

### Deploy to Render (Recommended)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. **Fork this repository** on GitHub
2. **Sign up** for a [Render](https://render.com) account
3. **Create a PostgreSQL database** on Render
4. **Create a Web Service** and connect your GitHub repository
5. **Configure environment variables** in Render dashboard
6. **Deploy!** 🚀

### Alternative Deployment Options

- **Heroku**: Use `Procfile` included in repository
- **AWS**: Deploy using Elastic Beanstalk or EC2
- **DigitalOcean**: Use App Platform or Droplets
- **VPS**: Traditional server deployment with Gunicorn + Nginx

---

## 🏗️ Architecture

```
NeethiAI/
│
├── 📄 neethi.py                 # Main Flask application
├── 📋 requirements.txt          # Python dependencies
├── 🚀 render.yaml              # Render deployment config
├── 📝 Procfile                 # Heroku deployment config
│
├── 📁 static/                  # Static assets
│   ├── 📁 icons/
│   │   └── logo.jpg            # Application logo
│   ├── 📁 css/
│   │   └── style.css           # Custom styles (Professional dark theme)
│   └── manifest.json           # PWA manifest
│
├── 📁 templates/               # HTML templates
│   ├── base.html              # Base template with navigation
│   ├── index.html             # Landing page
│   ├── auth.html              # Login/Register page
│   ├── chat.html              # Main chat interface
│   ├── profile.html           # User profile page
│   └── dashboard.html         # Dashboard redirect
│
├── 📖 README.md               # This file
├── 📚 RENDER_DEPLOYMENT.md    # Deployment guide
└── 📄 LICENSE                 # MIT License
```

### Key Components

- **Backend**: Flask application with SQLAlchemy ORM
- **Database**: PostgreSQL for persistent storage
- **Frontend**: Bootstrap 5 + Custom CSS (Professional dark theme)
- **Authentication**: Flask-Login with OAuth support
- **Document Processing**: PyPDF2, python-docx, EasyOCR

---

## 🛠️ Tech Stack

### Backend

- **Flask** 2.3+ - Web framework
- **SQLAlchemy** - ORM for database operations
- **PostgreSQL** - Relational database
- **Flask-Login** - User session management
- **Authlib** - OAuth integration

### AI & Processing

- **Google Gemini API** - AI-powered legal responses
- **EasyOCR** - OCR for document and image processing
- **langdetect** - Automatic language detection
- **PyPDF2** - PDF document parsing
- **python-docx** - Word document processing
- **Pillow** - Image processing

### Frontend

- **Bootstrap 5** - Responsive UI framework
- **JavaScript (ES6+)** - Interactive functionality
- **Font Awesome** - Icon library
- **Google Fonts** - Typography (Inter, Noto Sans Tamil)
- **Marked.js** - Markdown rendering

### DevOps & Deployment

- **Render** - Cloud hosting platform
- **PostgreSQL** - Managed database
- **Git** - Version control
- **PWA** - Progressive Web App support

---

## 📱 Mobile Support

NeethiAI is fully responsive and optimized for mobile devices:

### Features

- ✅ **Responsive Design**: Adapts to all screen sizes
- ✅ **Touch-Friendly**: Optimized for touch interactions
- ✅ **PWA Support**: Installable as a mobile app
- ✅ **Mobile Menu**: Collapsible sidebar navigation
- ✅ **Voice Input**: Mobile-optimized speech recognition
- ✅ **File Upload**: Mobile file picker integration

### Installation on Mobile

1. Open NeethiAI in your mobile browser
2. Look for "Add to Home Screen" option
3. Install with custom NeethiAI logo
4. Access like a native app!

---

## 🤝 Contributing

Contributions are welcome! This is a final-year project, and we appreciate any improvements.

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes**
4. **Commit your changes** (`git commit -m 'Add amazing feature'`)
5. **Push to the branch** (`git push origin feature/amazing-feature`)
6. **Open a Pull Request**

### Contribution Guidelines

- Follow PEP 8 Python style guide
- Write clear commit messages
- Add comments for complex logic
- Test your changes thoroughly
- Update documentation if needed

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2026 NeethiAI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 🙏 Acknowledgments

### Technologies & Libraries

- **Google Gemini AI** - For powerful language processing capabilities
- **Flask Community** - For the excellent web framework
- **Bootstrap Team** - For responsive UI components
- **PostgreSQL** - For robust database management

### Inspiration

- Built with ❤️ for the Indian legal community
- Designed to make legal information accessible to everyone
- Inspired by the need for bilingual legal assistance

### Special Thanks

- All contributors and users who provided feedback
- Open-source community for amazing tools and libraries
- Final year project advisors and reviewers

---

## 📞 Support & Contact

- **🌐 Website**: [neethiai.com](https://neethiai.com)
- **🐛 Issues**: [GitHub Issues](https://github.com/yourusername/neethiai/issues)
- **📖 Documentation**: [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md)
- **📧 Email**: support@neethiai.com

---

<div align="center">

### ⚖️ Made with ❤️ for the Indian Legal Community

**NeethiAI** - Your Trusted Legal AI Companion  
**© 2026 HariDharaan — All rights reserved.**

[⬆ Back to Top](#-neethiai)

</div>
