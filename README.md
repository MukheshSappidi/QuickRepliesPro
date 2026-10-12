# ⚡ Quick Replies Pro

A blazing-fast, lightweight open-source desktop quick-reply utility built for power users, customer support agents, and professionals using WhatsApp Business, CRM systems, or any text-heavy application on Windows.

![Dashboard Preview](assets/dashboard_preview.png)

---

## ✨ Key Features

- **Dual Global Hotkey Triggers**: Instantly invoke your search popup anywhere using **`Alt + Q`** or the single backtick key (**`` ` ``**) positioned right above your Tab key.
- **Zero Key Conflicts**: Engineered to completely bypass native app shortcut restrictions (such as standard chat app `/` limitations).
- **Smart Real-Time Filtering**: Type a keyword or shortcut fragment to instantly filter through hundreds of custom templates.
- **Lightning-Fast Auto-Paste Engine**: Automatically copies your selected template to the system clipboard and simulates `Ctrl + V` to drop the text seamlessly into your active chat window.
- **Persistent SQLite Backend**: Local data storage with full usage tracking and statistics (`Total replies` and `Total uses`).
- **JSON Portability**: Easily import or export your template library for backups or sharing with team members.
- **System Tray Integration**: Runs quietly in your Windows system tray without cluttering your taskbar.

---

## 🛠️ Tech Stack

- **Language**: Python 3.10+
- **GUI Framework**: PySide6 (Qt for Python)
- **Global Hooks**: `keyboard` library
- **Clipboard & Automation**: `pyperclip` & `pyautogui`
- **Database**: `sqlite3`

---

## 🚀 Getting Started (For Users & Developers)

### 1. Prerequisites
Ensure you have **Python 3.10 or higher** installed on your Windows machine.

### 2. Clone or Download the Repository
Download the project zip or clone the repository via Git:
```bash
git clone [https://github.com/your-username/QuickRepliesPro.git](https://github.com/your-username/QuickRepliesPro.git)
cd QuickRepliesPro