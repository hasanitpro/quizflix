<?php
session_start();
require_once '../includes/db.php';
include 'templates/header.php';

$message = "";

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['quiz_file'])) {
    $file = $_FILES['quiz_file']['tmp_name'];
    $handle = fopen($file, 'r');

    if ($handle !== false) {
        fgetcsv($handle); // Skip header row
        $pdo->beginTransaction();
        $quizCache = [];

        try {
            while (($row = fgetcsv($handle, 1000, ',')) !== false) {
                if (count($row) < 14) continue;

                [
                    $quizTitle, $introText, $outroText, $bgMusic, $chalkSound,
                    $correctSound, $backgroundImage, $questionText, $opt1,
                    $opt2, $opt3, $opt4, $correctIndex, $funFact
                ] = $row;

                // Cache and insert quiz only once
                if (!isset($quizCache[$quizTitle])) {
                    $stmt = $pdo->prepare("SELECT id FROM quizzes WHERE title = ?");
                    $stmt->execute([$quizTitle]);
                    $quizId = $stmt->fetchColumn();

                    if (!$quizId) {
                        $stmt = $pdo->prepare("INSERT INTO quizzes (title, intro_text, outro_text, bg_music, chalk_sound, correct_sound, background_image) VALUES (?, ?, ?, ?, ?, ?, ?)");
                        $stmt->execute([$quizTitle, $introText, $outroText, $bgMusic, $chalkSound, $correctSound, $backgroundImage]);
                        $quizId = $pdo->lastInsertId();
                    } else {
                        $stmt = $pdo->prepare("UPDATE quizzes SET intro_text = ?, outro_text = ?, bg_music = ?, chalk_sound = ?, correct_sound = ?, background_image = ? WHERE id = ?");
                        $stmt->execute([$introText, $outroText, $bgMusic, $chalkSound, $correctSound, $backgroundImage, $quizId]);
                    }

                    $quizCache[$quizTitle] = $quizId;
                } else {
                    $quizId = $quizCache[$quizTitle];
                }

                // Skip if question already exists
                $stmt = $pdo->prepare("SELECT id FROM questions WHERE quiz_id = ? AND question_text = ?");
                $stmt->execute([$quizId, $questionText]);
                $existingQuestionId = $stmt->fetchColumn();
                if ($existingQuestionId) continue;

                // Insert question
                $stmt = $pdo->prepare("INSERT INTO questions (quiz_id, question_text, correct_index, fun_fact) VALUES (?, ?, ?, ?)");
                $stmt->execute([$quizId, $questionText, intval($correctIndex), $funFact]);
                $questionId = $pdo->lastInsertId();

                // Insert options with correct flag
                $options = [$opt1, $opt2, $opt3, $opt4];
                foreach ($options as $i => $opt) {
                    $isCorrect = ($i + 1 == intval($correctIndex)) ? 1 : 0;
                    $stmt = $pdo->prepare("INSERT INTO options (question_id, option_index, option_text, is_correct) VALUES (?, ?, ?, ?)");
                    $stmt->execute([$questionId, $i + 1, $opt, $isCorrect]);
                }
            }

            $pdo->commit();
            $_SESSION['message'] = "✅ Quiz imported successfully.";
            header("Location: index.php");
            exit;

        } catch (Exception $e) {
            $pdo->rollBack();
            $message = "❌ Error during import: " . $e->getMessage();
        }

        fclose($handle);
    } else {
        $message = "❌ Failed to read the uploaded file.";
    }
}
?>

<a class="back-link" href="index.php">← Back to Dashboard</a>
<h2>📤 Upload Quiz CSV</h2>

<form method="POST" enctype="multipart/form-data">
    <input type="file" name="quiz_file" accept=".csv" required />
    <br /><br />
    <button type="submit" class="save">Upload & Import</button>
</form>

<?php if ($message): ?>
<p class="message"><?= htmlspecialchars($message) ?></p>
<?php endif; ?>

<?php include 'templates/footer.php'; ?>