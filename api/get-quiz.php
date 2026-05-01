<?php
require_once '../includes/db.php';
header('Content-Type: application/json');

$quizId = isset($_GET['id']) ? intval($_GET['id']) : 0;

if (!$quizId) {
    http_response_code(400);
    echo json_encode(["error" => "Quiz ID is required."]);
    exit;
}

try {
    // Get quiz metadata
    $stmt = $pdo->prepare("
        SELECT title, intro_text, outro_text, bg_music, chalk_sound, correct_sound, background_image 
        FROM quizzes 
        WHERE id = ?
    ");
    $stmt->execute([$quizId]);
    $quiz = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$quiz) {
        http_response_code(404);
        echo json_encode(["error" => "Quiz not found."]);
        exit;
    }

    // Get questions
    $questionStmt = $pdo->prepare("SELECT * FROM questions WHERE quiz_id = ?");
    $questionStmt->execute([$quizId]);
    $questions = $questionStmt->fetchAll(PDO::FETCH_ASSOC);

    $quizData = [];

    foreach ($questions as $question) {
        // Get options for each question
        $optionStmt = $pdo->prepare("
            SELECT option_index, option_text 
            FROM options 
            WHERE question_id = ? 
            ORDER BY option_index ASC
        ");
        $optionStmt->execute([$question['id']]);
        $options = $optionStmt->fetchAll(PDO::FETCH_KEY_PAIR);

        $quizData[] = [
            "q" => $question['question_text'],
            "o" => array_values($options),
            "c" => (int)$question['correct_index'],
            "f" => $question['fun_fact']
        ];
    }

    // Return full quiz object
    echo json_encode([
        "title" => $quiz['title'],
        "introText" => $quiz['intro_text'],
        "outroText" => $quiz['outro_text'],
        "bgMusic" => $quiz['bg_music'],
        "chalkSound" => $quiz['chalk_sound'],
        "correctSound" => $quiz['correct_sound'],
        "backgroundImage" => $quiz['background_image'],
        "questions" => $quizData
    ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(["error" => "Server error: " . $e->getMessage()]);
}