<?php
require_once '../includes/db.php';
header('Content-Type: application/json');

try {
    $stmt = $pdo->query("SELECT id, title FROM quizzes ORDER BY created_at DESC");
    $quizzes = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode($quizzes, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(["error" => "Failed to load quizzes."]);
}