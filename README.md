# MansionNET QuizBot 🎮

An advanced IRC trivia bot powered by Mistral AI that provides engaging quiz games with real-time scoring, user statistics, and multiple categories.

## Features 🌟

- AI-powered trivia questions using Mistral AI
- Multiple question categories including Pop Culture, Sports, Science & Tech
- Dynamic scoring system with streak and speed bonuses
- Real-time leaderboards and player statistics
- SQLite database for persistent storage
- Advanced answer matching system with typo tolerance
- Rate limiting and quota management
- Colorful IRC message formatting

## Requirements 📋

- Python 3.8+
- Mistral AI API key
- SQLite3
- IRC Server connection

## Installation 🛠️

1. Clone the repository:
   ```bash
   git clone https://github.com/MansionNET/QuizBot.git
   cd QuizBot
   ```

2. Create and activate virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create .env file with your Mistral AI API key:
   ```bash
   MISTRAL_API_KEY=your_api_key_here
   ```

## Configuration ⚙️

Edit the bot settings in `src/mansionnet/quizbot.py`:
- IRC server and port
- Channel list
- Rate limits
- Quiz settings

## Usage 🎯

Run the bot:
```bash
python3 src/mansionnet/quizbot.py
```

### Bot Commands

- `!quiz` - Start a new quiz game
- `!help` - Show help message and rules
- `!stats` - View your quiz statistics
- `!leaderboard` - Show top players
- `!stop` - Stop current quiz (admin only)

### Quiz Features

- 10 questions per game
- 30 seconds to answer each question
- Bonus points for quick answers and streaks
- Multiple difficulty levels
- Wide range of topics
- Dynamic scoring system

## Contributing 🤝

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits 👥

Created by Avatar for MansionNET IRC Network

## Support 💬

For support, join us on IRC:
- Server: irc.inthemansion.com
- Port: 6697 (SSL)
- Channel: #help