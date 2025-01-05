# MansionNet QuizBot

An IRC-based trivia game bot powered by Mistral AI for dynamic question generation. The bot provides engaging real-time quiz games with features like score tracking, bonus points, and comprehensive statistics.

## Features

### Core Functionality
- Dynamic question generation using Mistral AI
- Real-time IRC interaction
- Multiple difficulty levels (Easy: 60%, Medium: 30%, Hard: 10%)
- Multi-channel support
- Persistent score tracking
- Global leaderboards

### Game Features
- 10 questions per game session
- 30-second answer window per question
- Speed-based scoring system (1-10 points)
- Streak bonuses up to 2.5x multiplier
- Quick answer bonuses up to 2.0x multiplier
- Player statistics tracking
- Answer validation with fuzzy matching

### Question Categories
- Pop Culture (Movies, TV, Music, Social Media)
- Sports & Games
- Science & Tech
- History & Current Events
- General Knowledge

## Setup

### Prerequisites
- Python 3.8 or higher
- Mistral AI API key
- Access to an IRC server

### Installation
1. Clone the repository:
```bash
git clone https://github.com/yourusername/quizbot.git
cd quizbot
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

4. Create a .env file with your Mistral AI API key:
```bash
MISTRAL_API_KEY=your_api_key_here
```

### Configuration
Edit `src/mansionnet/config/settings.py` to configure:
- IRC server details
- Channel names
- Admin users
- Game parameters
- Scoring rules

## Usage

### Running the Bot
```bash
python -m src.mansionnet
```

### IRC Commands
- `!quiz` - Start a new quiz game
- `!help` - Show commands and rules
- `!stats` - View your statistics
- `!leaderboard` - Show top players
- `!stop` - Stop current quiz (admin only)

### Game Rules

#### Basic Rules
1. Each game consists of 10 questions
2. Players have 30 seconds to answer each question
3. Type answers directly in the channel
4. First correct answer wins the points
5. Faster answers earn more points

#### Scoring System
1. Base Points (1-10)
   - Based on answer speed
   - Maximum points for instant answers
   - Minimum 1 point for last-second answers

2. Streak Bonuses
   - 3 correct answers: 1.5x multiplier
   - 5 correct answers: 2.0x multiplier
   - 7 correct answers: 2.5x multiplier

3. Speed Bonuses
   - 5+ seconds remaining: 1.5x multiplier
   - 3+ seconds remaining: 2.0x multiplier

#### Answer Validation
- Case insensitive
- Ignores articles (a, an, the)
- Supports common abbreviations
- Handles singular/plural variations
- Accepts partial answers for long names

## Project Structure
```
mansionnet/
├── config/           # Configuration files
├── core/            # Core game logic
├── models/          # Data models
├── services/        # External services (Mistral, IRC)
└── utils/           # Helper utilities
```

## Technical Details

### Database Schema

#### scores table
```sql
CREATE TABLE scores (
    username TEXT PRIMARY KEY,
    total_score INTEGER DEFAULT 0,
    games_played INTEGER DEFAULT 0,
    correct_answers INTEGER DEFAULT 0,
    fastest_answer REAL DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    highest_score INTEGER DEFAULT 0,
    last_played TIMESTAMP
)
```

#### question_history table
```sql
CREATE TABLE question_history (
    question_hash TEXT PRIMARY KEY,
    question TEXT,
    answer TEXT,
    category TEXT,
    times_asked INTEGER DEFAULT 0,
    times_answered_correctly INTEGER DEFAULT 0,
    last_asked TIMESTAMP,
    average_answer_time REAL DEFAULT 0
)
```

### Question Generation
The bot uses Mistral AI with carefully crafted prompts to ensure:
- Questions are well-known and mainstream
- Answers are unambiguous
- Content is engaging and current
- Questions are appropriate difficulty

### IRC Integration
- SSL/TLS support
- Auto-reconnect on disconnection
- Message rate limiting
- Color and formatting support
- Channel mode awareness

## Development

### Adding New Features

#### New Question Types
1. Modify `services/mistral_service.py`
2. Update prompt templates
3. Add validation rules

#### Custom Game Modes
1. Extend `core/quiz_game.py`
2. Add mode-specific scoring rules
3. Update database schema if needed

#### UI Improvements
1. Modify IRC message formatting in `services/irc_service.py`
2. Add new color schemes in settings
3. Update command responses

### Testing
Create test files in `tests/` directory following the module structure.

## Troubleshooting

### Common Issues
1. Connection Problems
   - Verify IRC server details
   - Check SSL certificate settings
   - Confirm network connectivity

2. Question Generation
   - Validate Mistral AI API key
   - Check API rate limits
   - Monitor response quality

3. Database Issues
   - Verify file permissions
   - Check disk space
   - Monitor connection pool

### Logging
- Location: `logs/quizbot.log`
- Levels: DEBUG, INFO, WARNING, ERROR
- Rotation: Daily with 7-day retention

## Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes following the code style
4. Submit a pull request

## License
This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments
- Mistral AI for the question generation API
- IRC protocol specification
- SQLite for database management