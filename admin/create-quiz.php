<?php
require_once '../includes/db.php';
include 'templates/header.php';

$title = '';
$intro_text = '';
$outro_text = '';
$message = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $title = trim($_POST['title']);
    $intro_text = trim($_POST['intro_text']);
    $outro_text = trim($_POST['outro_text']);

    if ($title) {
        $stmt = $pdo->prepare("INSERT INTO quizzes (title, intro_text, outro_text, created_at) VALUES (?, ?, ?, NOW())");
        $stmt->execute([$title, $intro_text, $outro_text]);
        $newQuizId = $pdo->lastInsertId();
        header("Location: edit.php?id=$newQuizId");
        exit;
    } else {
        $message = '❗ Quiz title is required.';
    }
}
?>
<p><a href="index.php">← Back to Dashboard</a></p>
<h2>➕ Create New Quiz</h2>

<?php if ($message): ?>
<p style="color:red;"><?= htmlspecialchars($message) ?></p>
<?php endif; ?>

<form method="POST">
    <label>Title:</label><br>
    <input type="text" name="title" value="<?= htmlspecialchars($title) ?>" required><br><br>

    <label>Intro Text:</label><br>
    <textarea name="intro_text" rows="4"><?= htmlspecialchars($intro_text) ?></textarea><br><br>

    <label>Outro Text:</label><br>
    <textarea name="outro_text" rows="4"><?= htmlspecialchars($outro_text) ?></textarea><br><br>

    <button type="submit" class="button">💾 Create Quiz</button>
</form>

<?php include 'templates/footer.php'; ?>