<?php
$quizId  = isset($_GET['id']) ? intval($_GET['id']) : null;
$preview = isset($_GET['preview']) && $_GET['preview'] === 'true';
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AZ Quiz Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Fredoka:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="public/css/style.css" />
</head>
<body>

    <!-- Quiz Selector -->
    <div class="quiz-container<?= ($preview || $quizId) ? ' hidden' : '' ?>" id="quiz-selector">
        <h1>📚 Select a Quiz to Begin</h1>
        <select id="quiz-dropdown">
            <option disabled selected>-- Choose a Quiz --</option>
        </select>
        <br />
        <button id="load-quiz-btn">Start Quiz</button>
    </div>

    <!-- Quiz Interface -->
    <div class="quiz-container<?= (!$preview && !$quizId) ? ' hidden' : '' ?>" id="quiz">

        <!-- Progress bar (hidden until quiz starts) -->
        <div id="quiz-progress" class="hidden">
            <span id="progress-label">Question 1 of 10</span>
            <div class="progress-track"><div id="progress-fill"></div></div>
        </div>

        <div class="intro-screen">
            <h1>🎓 Welcome to AZ Quiz Hub!</h1>
            <p>Today's quiz is not for the faint of heart. Think you're a genius?<br />
                Let's see if you can answer these trivia questions! 😎</p>
            <p>⏳ You'll have 10 seconds per question. Good luck!</p>
            <button id="start-btn">Start Quiz</button>
            <button id="fullscreen-btn" style="display:none; margin:2rem auto 0;">Go Fullscreen &amp; Start Quiz</button>
            <div id="countdown-overlay">
                Starting in <span id="countdown">5</span>...
            </div>
        </div>
    </div>

    <!-- Score badge (fixed top-right, shown during quiz) -->
    <div id="quiz-score" class="hidden">
        Score: <span id="score-value">0</span> / <span id="score-total">0</span>
    </div>

    <!-- Audio -->
    <audio id="bg-music" loop></audio>
    <audio id="chalk-sound"></audio>
    <audio id="correct-chime"></audio>

    <img src="public/assets/logo.png" alt="AZ Quiz Hub Logo" id="quiz-logo">

    <script src="public/js/script.js"></script>
</body>
</html>
