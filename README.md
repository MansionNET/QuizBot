# QuizBot

An IRC-based trivia bot powered by Mistral AI for dynamic question generation. QuizBot creates engaging quiz games with automatically generated questions across various categories, featuring scoring systems, player statistics, and multiplayer support.

## IRC Server Details

Join us on MansionNET IRC to chat with us, test the bot, and play some trivia! 

🌐 **Server:** irc.inthemansion.com  
🔒 **Port:** 6697 (SSL)  
📝 **Channel:** #opers, #general, #welcome, #devs (and many others)

## Features

- **Dynamic Question Generation**: Uses Mistral AI to create unique, contextually relevant questions
- **Multiple Categories**: Covers science, history, geography, arts, sports, technology, nature, space, literature, and music
- **Scoring System**: Features streak multipliers and speed-based scoring
- **Player Statistics**: Tracks scores, correct answers, best streaks, and fastest answers
- **Admin Controls**: Moderation tools for game management
- **Persistent Storage**: SQLite database for questions and player stats
- **Rate Limiting**: Smart token bucket implementation for API calls

## Commands

- `!quiz` - Start a new quiz game
- `!stats` - Show your statistics
- `!leaderboard` - Show top players
- `!help` - Display help message
- `!stop` - Stop the current game (admin only)

## Requirements

- Python 3.9+
- Mistral AI API key
- IRC server access

## Installation

1. Clone the repository:
```bash
git clone https://github.com/mansionNET/QuizBot.git
cd QuizBot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your configuration:
```env
IRC_SERVER=irc.example.com
IRC_PORT=6697
IRC_NICKNAME=QuizBot
IRC_CHANNELS=#channel1,#channel2
ADMIN_USERS=admin1,admin2
MISTRAL_API_KEY=your_api_key_here
DATABASE_URL=sqlite:///quiz.db
```

## Usage

1. Ensure your `.env` file is configured correctly
2. Run the bot:
```bash
python src/main.py
```

## Project Structure

```
quizbot/
├── src/
│   ├── models/
│   │   ├── database.py
│   │   ├── question.py
│   │   └── quiz_state.py
│   ├── services/
│   │   ├── irc_service.py
│   │   └── mistral_service.py
│   ├── utils/
│   │   ├── scoring.py
│   │   └── text_processing.py
│   ├── bot.py
│   ├── config.py
│   ├── game_manager.py
│   └── main.py
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

## Configuration Options

- `QUESTION_TIMEOUT`: Time allowed for answering each question (default: 30 seconds)
- `MIN_ANSWER_TIME`: Minimum time between answers to prevent spam (default: 1.0 seconds)
- `BASE_POINTS`: Base points for correct answers (default: 100)
- `QUESTIONS_PER_GAME`: Number of questions per game (default: 10)
- `SPEED_MULTIPLIER_MAX`: Maximum speed bonus multiplier (default: 2.0)

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Mistral AI](https://mistral.ai/) for question generation
- Uses [Python IRC](https://python-irc.readthedocs.io/) for IRC connectivity
- SQLAlchemy for database management
