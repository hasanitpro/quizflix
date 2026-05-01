<?php
require_once '../includes/db.php';

if (!isset($_GET['id']) || !is_numeric($_GET['id'])) {
    die('Invalid ID');
}

$id = intval($_GET['id']);

// Delete related questions and options first
$pdo->beginTransaction();
try {
    $stmt = $pdo->prepare("DELETE FROM options WHERE question_id IN (SELECT id FROM questions WHERE quiz_id = ?)");
    $stmt->execute([$id]);

    $stmt = $pdo->prepare("DELETE FROM questions WHERE quiz_id = ?");
    $stmt->execute([$id]);

    $stmt = $pdo->prepare("DELETE FROM quizzes WHERE id = ?");
    $stmt->execute([$id]);

    $pdo->commit();
    session_start();
    $_SESSION['message'] = "🗑️ Quiz deleted successfully.";
    header("Location: index.php");
    exit;
} catch (Exception $e) {
    $pdo->rollBack();
    die("Error deleting quiz: " . $e->getMessage());
}