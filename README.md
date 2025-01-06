# MansionNet QuizBot

An IRC-based trivia game bot powered by Mistral AI for dynamic question generation. The bot provides engaging real-time quiz games with features like score tracking, bonus points, and comprehensive statistics.

## Recent Improvements (January 2025)
- Enhanced question validation with multiple retry attempts
- Improved error handling for API failures
- More diverse question generation across multiple categories
- Added informative fun facts after each answer
- Fixed question repetition issues
- Improved answer matching system with better handling of:
  - Diacritics (e.g., "Gaudí" vs "Gaudi")
  - Common name variations
  - Alternative spellings
  - Name variations (e.g., "da Vinci" vs "Leonardo")
  - Historical references

## Features

### Core Functionality
- Dynamic question generation using Mistral AI
- Real-time IRC interaction
- Multiple difficulty levels (Easy: 60%, Medium: 30%, Hard: 10%)
- Multi-channel support
- Persistent score tracking
- Global leaderboards
- Fun facts for every question

### Game Features
- 10 questions per game session
- 30-second answer window per question
- Speed-based scoring system (1-10 points)
- Streak bonuses up to 2.5x multiplier
- Quick answer bonuses up to 2.0x multiplier
- Player statistics tracking
- Answer validation with fuzzy matching
- Educational fun facts after each question

### Question Categories
- Science & Technology
  - Physics & Space
  - Biology & Nature
  - Computing & Tech
  - Environmental Science
- History & Geography
  - Ancient Civilizations
  - World History
  - Countries & Capitals
  - Famous Landmarks
- Arts & Culture
  - Classical Music
  - Literature & Authors
  - Painting & Sculpture
  - Architecture
- Entertainment
  - Classic Movies
  - Television
  - Video Games
  - Sports & Athletics

## Example Game Session
```
[19:00:56] <QuizBot> 🎯 New Quiz Starting!
[19:00:56] <QuizBot> • Type your answer in the channel
[19:00:56] <QuizBot> • 30 seconds per question
[19:00:56] <QuizBot> • 10 questions total
[19:00:56] <QuizBot> • Faster answers = More points
[19:00:56] <QuizBot> • Get bonus points for answer streaks
[19:00:58] <QuizBot> Question 1/10: Who painted the Mona Lisa?
[19:01:03] <Player1> da vinci
[19:01:03] <QuizBot> ✨ Player1 got 7 points! (Base: 5 × Bonus: 1.5)
[19:01:03] <QuizBot> 💡 The Mona Lisa was painted in the early 16th century.
```

## Setup

### Prerequisites
- Python 3.8 or higher
- Mistral AI API key
- Access to an IRC server
- SQLite3 (included in Python)

### Installation

#### Linux/macOS
1. Clone the repository:
```bash
git clone https://github.com/yourusername/quizbot.git
cd quizbot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a .env file with your Mistral AI API key:
```bash
MISTRAL_API_KEY=your_api_key_here
```

#### Windows
1. Clone the repository:
```cmd
git clone https://github.com/yourusername/quizbot.git
cd quizbot
```

2. Create and activate a virtual environment:
```cmd
python -m venv venv
venv\Scripts\activate
```

3. Install dependencies:
```cmd
pip install -r requirements.txt
```

4. Create a .env file with your Mistral AI API key:
```cmd
echo MISTRAL_API_KEY=your_api_key_here > .env
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
6. After each answer, a fun fact is shared

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
- Handles diacritics and special characters
- Recognizes common name variations
- Supports alternative spellings

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
- Each question includes an interesting fun fact
- Multiple retry attempts with appropriate delays
- Fallback questions for API failures

### Reliability Features
- Graceful handling of API failures
- Multiple retry attempts for question generation
- Smart question validation system
- Proper delay between retries to avoid rate limits
- Comprehensive error logging
- State management protection
- Fallback question system

### IRC Integration
- SSL/TLS support
- Auto-reconnect on disconnection
- Message rate limiting
- Color and formatting support
- Channel mode awareness

## Common Issues and Solutions

### Connection Problems
1. Bot fails to connect to IRC server
   - Verify server address and port in settings.py
   - Check if SSL/TLS is required
   - Ensure server allows bot connections

2. Bot connects but doesn't join channels
   - Verify channel names are correct (including #)
   - Check if channels require authentication
   - Ensure bot has necessary permissions

### Question Generation
1. Questions stop generating
   - Check Mistral AI API key validity
   - Verify API rate limits haven't been exceeded
   - Check network connectivity
   - The bot will automatically retry and use fallback questions

2. Questions seem repetitive
   - Check question_history table isn't full
   - Verify category distribution settings
   - Clear question history if necessary

3. Answer validation issues
   - Add common variations to ALTERNATIVE_ANSWERS in settings
   - Adjust fuzzy matching threshold
   - Update diacritic mappings

### Database Issues
1. Database errors
   - Check file permissions on quiz.db
   - Verify SQLite version compatibility
   - Ensure sufficient disk space
   - Backup database regularly

### Performance
1. Bot becomes slow
   - Monitor API response times
   - Check database query performance
   - Reduce number of concurrent channels
   - Adjust question timeouts

2. High resource usage
   - Monitor memory usage
   - Check for connection leaks
   - Reduce logging verbosity
   - Adjust database connection pool

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