> # ⚠️ This repository has moved
>
> **QuizBot** is now developed at **[git.inthemansion.com/MansionNET/QuizBot](https://git.inthemansion.com/MansionNET/QuizBot)**.
>
> This GitHub copy is **archived and read-only** — it will not receive further updates.
> Please update your remotes:
>
> ```
> git remote set-url origin git@git.inthemansion.com:MansionNET/QuizBot.git
> ```

---

# QuizBot for IRC

A sophisticated IRC quiz bot powered by Mistral AI that delivers engaging trivia games with dynamic question generation and rich features.

## 🌐 IRC Server Details

Join us on MansionNET IRC to chat with us, test the bot, and play some trivia! 

- **Server:** irc.inthemansion.com  
- **Port:** 6697 (SSL)  
- **Channel:** #opers, #general, #welcome, #devs (and many others)

## 🌟 Features

- **AI-Powered Questions**: Uses Mistral AI to generate unique, engaging questions across multiple categories
- **Dynamic Game System**: Run multiple concurrent quiz games in different IRC channels
- **Smart Scoring**: Points system based on answer speed and winning streaks
- **Rich Categories**: Questions from various domains including geography, history, science, arts, entertainment, sports, and more
- **Player Statistics**: Track player performance, streaks, and maintain leaderboards
- **Fallback System**: Built-in backup questions ensure continuous operation even if AI service is unavailable

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- SQLite3
- Mistral AI API key
- IRC server access

### Installation

1. Clone the repository:
```bash
git clone https://github.com/mansionNET/QuizBot.git
cd quizbot_mansionnet
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy the example environment file:
```bash
cp .env.example .env
```

5. Edit `.env` with your configuration:
```env
MISTRAL_API_KEY=your_api_key_here
IRC_SERVER=irc.inthemansion.com
IRC_PORT=6697
IRC_NICKNAME=QuizBot
IRC_CHANNELS=#yourchannel
ADMIN_USERS=admin1,admin2
QUESTIONS_PER_GAME=10
QUESTION_TIMEOUT=30
MIN_QUESTIONS=20
```

### Running the Bot

Start the bot:
```bash
python src/main.py
```

## 🎮 Game Commands

- `!quiz` - Start a new quiz game
- `!help` - Show available commands
- `!stats` - Display your game statistics
- `!leaderboard` - Show top players
- `!stop` - Stop the current game (admin only)

## 🎯 Game Rules

1. Each game consists of a configurable number of questions (default: 10)
2. Players have a limited time to answer each question (default: 30 seconds)
3. Points are awarded based on:
   - Speed of answer (faster = more points)
   - Answer streak (consecutive correct answers multiply points)
4. Only the first correct answer for each question counts
5. Multiple answer formats are accepted for flexibility

## 🛠️ Configuration

Key configuration options in `.env`:

- `QUESTIONS_PER_GAME`: Number of questions per game session
- `QUESTION_TIMEOUT`: Seconds allowed for answering each question
- `MIN_QUESTIONS`: Minimum questions to keep in database
- `BASE_POINTS`: Base points for correct answers
- `SPEED_MULTIPLIER_MAX`: Maximum multiplier for quick answers

## 📚 Question Categories

- Geography
- History
- Science
- Arts
- Entertainment
- Sports
- Food & Drink
- Nature

## 🧩 Technical Architecture

- **IRC Service**: Handles IRC connection and message routing
- **Game Manager**: Manages game states and player interactions
- **Question Service**: Generates and manages questions using Mistral AI
- **Database**: SQLite storage for questions and player statistics
- **Utilities**: Answer validation, scoring, and text processing

## 🔧 Development

### Project Structure
```
quizbot_mansionnet/
├── src/
│   ├── models/                   # Data models
│   │   ├── __init__.py
│   │   ├── database.py           # Database connection and queries
│   │   ├── question.py           # Question management
│   │   └── quiz_state.py         # Quiz game state handling
│   ├── services/                 # Core services
│   │   ├── __init__.py
│   │   ├── irc_service.py        # IRC connection handling
│   │   ├── mistral_service.py    # AI question generation
│   │   └── question_service.py   # Question management service
│   ├── utils/                    # Utility functions
│   │   ├── __init__.py
│   │   ├── answer_normalizer.py  # Answer validation
│   │   ├── scoring.py            # Points calculation
│   │   ├── text_processing.py    # Text manipulation utilities
│   │   └── validators.py         # Input validation
│   ├── __init__.py
│   ├── bot.py                    # Main bot class
│   ├── config.py                 # Configuration handling
│   ├── game_manager.py           # Game state management
│   └── main.py                   # Entry point
├── .env                          # Environment configuration
├── requirements.txt              # Python dependencies
├── setup.py                      # Package setup
```

### Adding New Features

1. Fork the repository
2. Create a feature branch
3. Add your changes
4. Write/update tests
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🙏 Acknowledgments

- Mistral AI for the question generation capabilities
- IRC community for testing and feedback
- All contributors and users

## 📞 Support

For support, please:
1. Check existing issues
2. Create a new issue with detailed description
3. Join our IRC channel for direct help
