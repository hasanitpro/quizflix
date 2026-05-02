<?php
/**
 * trigger-video.php  —  Manually trigger video generation + YouTube upload for a quiz.
 * Spawns run_daily.py with a specific quiz ID in the background.
 */
session_start();
require_once '../includes/db.php';

$quiz_id = intval($_GET['id'] ?? 0);
if ($quiz_id <= 0) {
    $_SESSION['message'] = 'Invalid quiz ID.';
    header('Location: index.php');
    exit;
}

// Verify quiz exists
$stmt = $pdo->prepare("SELECT title FROM quizzes WHERE id = ?");
$stmt->execute([$quiz_id]);
$quiz = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$quiz) {
    $_SESSION['message'] = 'Quiz not found.';
    header('Location: index.php');
    exit;
}

// Block if a video for this quiz already finished successfully
$done = $pdo->prepare("SELECT id FROM video_jobs WHERE quiz_id = ? AND status = 'done' LIMIT 1");
$done->execute([$quiz_id]);
if ($done->fetch()) {
    $_SESSION['message'] = "A video for \"{$quiz['title']}\" was already uploaded to YouTube. Generate a new quiz instead.";
    header('Location: index.php');
    exit;
}

// Block if a job is already in progress for this quiz
$check = $pdo->prepare("
    SELECT id FROM video_jobs
    WHERE quiz_id = ? AND status IN ('pending', 'generating', 'uploading')
    LIMIT 1
");
$check->execute([$quiz_id]);
if ($check->fetch()) {
    $_SESSION['message'] = "A video job is already in progress for \"{$quiz['title']}\". Please wait.";
    header('Location: index.php');
    exit;
}

// Insert the job row here so the dashboard shows "Pending" immediately.
// Pass the job ID to Python so it reuses this row instead of creating a duplicate.
$insert = $pdo->prepare("INSERT INTO video_jobs (quiz_id, status) VALUES (?, 'pending')");
$insert->execute([$quiz_id]);
$job_id = $pdo->lastInsertId();

$python   = 'C:\\Program Files\\Python311\\python.exe';
$script   = realpath(__DIR__ . '/../generator/run_daily.py');
$log_file = realpath(__DIR__ . '/../generator') . '\\quizflix_daily.log';

$cmd = "start /B \"\" \"{$python}\" \"{$script}\" --quiz-id {$quiz_id} --job-id {$job_id}";
pclose(popen($cmd, 'r'));

$_SESSION['message'] = "Video generation started for \"{$quiz['title']}\". Check the upload history below for progress.";
header('Location: index.php');
exit;
