<?php
session_start();
require_once '../includes/db.php';
include 'templates/header.php';

// Must match config.QUIZ_TOPICS in generator/config.py
$TOPICS = [
    "World Geography", "Ancient History", "Space & Astronomy",
    "Human Biology", "Famous Scientists", "World Capitals",
    "Classic Literature", "Pop Culture", "World Religions",
    "Mathematics & Logic", "Animals & Wildlife", "Technology & Computers",
    "Famous Inventions", "Movies & Cinema", "Music History",
    "Sports Trivia", "Food & Cuisine", "Famous Artworks",
    "World Languages", "Climate & Environment", "Economics & Finance",
    "Philosophy", "Mythology", "Architecture",
    "Medical Science", "Oceans & Marine Life", "Famous Leaders",
    "Astronomy & Black Holes", "Cryptography", "Aviation History",
    "The Human Brain", "Extreme Weather", "Dinosaurs & Prehistoric Life",
    "Ancient Civilisations", "Famous Quotes", "Video Games",
    "World Records", "Flags of the World", "Currency & Economics",
    "Famous Battles", "Chemistry Basics",
];

// Topics that already have at least one quiz generated
$stmt = $pdo->query("SELECT topic FROM quizzes WHERE topic IS NOT NULL AND topic != '' GROUP BY topic");
$usedTopics    = array_flip($stmt->fetchAll(PDO::FETCH_COLUMN));
$availableList = array_filter($TOPICS, fn($t) => !isset($usedTopics[$t]));
$usedList      = array_filter($TOPICS, fn($t) =>  isset($usedTopics[$t]));

$result = null; // ['type'=>'success'|'error', ...]

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $topic = trim($_POST['topic'] ?? '');
    $mode  = $_POST['mode'] ?? 'quiz_only';

    if (!$topic || !in_array($topic, $TOPICS)) {
        $result = ['type' => 'error', 'msg' => 'Invalid topic selected.'];
    } else {
        $python    = 'C:\\Program Files\\Python311\\python.exe';
        $genScript = realpath(__DIR__ . '/../generator/generate_quiz_ai.py');
        $genDir    = realpath(__DIR__ . '/../generator');
        $topicArg  = escapeshellarg($topic);

        // Run quiz generation synchronously (~5-10 seconds)
        $oldDir = getcwd();
        chdir($genDir);
        exec("\"{$python}\" \"{$genScript}\" --topic {$topicArg} 2>&1", $output, $exitCode);
        chdir($oldDir);

        if ($exitCode !== 0) {
            $result = ['type' => 'error', 'msg' => implode("\n", $output)];
        } else {
            // Find the quiz we just inserted
            $stmt = $pdo->prepare("
                SELECT id, title FROM quizzes WHERE topic = ? ORDER BY id DESC LIMIT 1
            ");
            $stmt->execute([$topic]);
            $newQuiz = $stmt->fetch(PDO::FETCH_ASSOC);

            if (!$newQuiz) {
                $result = ['type' => 'error', 'msg' => 'Quiz generated but not found in database.'];
            } elseif ($mode === 'full_pipeline') {
                $qid    = $newQuiz['id'];
                $insert = $pdo->prepare("INSERT INTO video_jobs (quiz_id, status) VALUES (?, 'pending')");
                $insert->execute([$qid]);
                $jobId = $pdo->lastInsertId();

                $runScript = realpath(__DIR__ . '/../generator/run_daily.py');
                $cmd = "start /B \"\" \"{$python}\" \"{$runScript}\" --quiz-id {$qid} --job-id {$jobId}";
                pclose(popen($cmd, 'r'));

                $_SESSION['message'] = "✅ AI quiz on \"{$topic}\" created (Quiz #{$qid}) and video pipeline started. Check upload history for progress.";
                header('Location: index.php');
                exit;
            } else {
                $result = ['type' => 'success', 'quiz' => $newQuiz, 'topic' => $topic];
            }
        }
    }
}
?>

<a class="back-link" href="index.php">← Back to Dashboard</a>
<h2>🤖 Generate AI Quiz</h2>

<?php if ($result && $result['type'] === 'success'): ?>
<div style="background:#d4edda;color:#155724;padding:1.5rem 2rem;border-radius:8px;
            border:1px solid #c3e6cb;margin-bottom:1.5rem;">
    <strong style="font-size:1.1rem;">✅ Quiz Created!</strong><br><br>
    <strong>Topic:</strong> <?= htmlspecialchars($result['topic']) ?><br>
    <strong>Title:</strong> <?= htmlspecialchars($result['quiz']['title']) ?><br>
    <strong>Quiz ID:</strong> #<?= (int)$result['quiz']['id'] ?>
    <p style="margin:1.2rem 0 0;">
        <a href="edit.php?id=<?= (int)$result['quiz']['id'] ?>" class="button">✏️ Edit Quiz</a>
        <a href="../index.php?id=<?= (int)$result['quiz']['id'] ?>&preview=true"
           class="button" target="_blank">👁 Preview</a>
        <a href="trigger-video.php?id=<?= (int)$result['quiz']['id'] ?>"
           class="button" style="background:#9c27b0;"
           onclick="return confirm('Generate video and upload to YouTube now?');">🎬 Upload to YouTube</a>
    </p>
</div>
<?php endif; ?>

<?php if ($result && $result['type'] === 'error'): ?>
<div style="background:#f8d7da;color:#721c24;padding:1.2rem 1.5rem;border-radius:8px;
            border:1px solid #f5c6cb;margin-bottom:1.5rem;white-space:pre-wrap;font-family:monospace;font-size:0.9rem;">
❌ <?= htmlspecialchars($result['msg']) ?>
</div>
<?php endif; ?>

<div style="background:white;padding:2rem;border-radius:8px;
            box-shadow:0 2px 8px rgba(0,0,0,0.1);max-width:620px;">

    <p style="color:#555;margin-top:0;line-height:1.6;">
        Gemini 2.5 Flash will write a 10-question quiz including title, intro, outro,
        YouTube description, and tags — all in one API call.<br>
        <strong style="color:#2e7d32;"><?= count($availableList) ?></strong> of
        <?= count($TOPICS) ?> topics not yet used.
    </p>

    <form method="post" id="genForm">

        <label>Topic</label>
        <select name="topic" required style="margin-bottom:1.4rem;">
            <option value="">— Select a topic —</option>
            <?php if ($availableList): ?>
            <optgroup label="✅ Not yet used (<?= count($availableList) ?>)">
                <?php foreach ($availableList as $t): ?>
                <option value="<?= htmlspecialchars($t) ?>"><?= htmlspecialchars($t) ?></option>
                <?php endforeach ?>
            </optgroup>
            <?php endif ?>
            <?php if ($usedList): ?>
            <optgroup label="🔄 Already used — will generate again (<?= count($usedList) ?>)">
                <?php foreach ($usedList as $t): ?>
                <option value="<?= htmlspecialchars($t) ?>"><?= htmlspecialchars($t) ?></option>
                <?php endforeach ?>
            </optgroup>
            <?php endif ?>
        </select>

        <label style="margin-top:0;">What to do after generating</label>
        <div style="margin-top:0.7rem;margin-bottom:1.8rem;display:flex;flex-direction:column;gap:0.8rem;">
            <label style="font-weight:normal;display:flex;align-items:flex-start;gap:10px;cursor:pointer;">
                <input type="radio" name="mode" value="quiz_only" checked style="width:auto;margin-top:3px;">
                <span>
                    <strong>Save quiz to database only</strong><br>
                    <span style="color:#666;font-size:0.9rem;">Instant. You can review and edit before generating the video.</span>
                </span>
            </label>
            <label style="font-weight:normal;display:flex;align-items:flex-start;gap:10px;cursor:pointer;">
                <input type="radio" name="mode" value="full_pipeline" style="width:auto;margin-top:3px;">
                <span>
                    <strong>Save quiz + generate video + upload to YouTube</strong><br>
                    <span style="color:#666;font-size:0.9rem;">Full pipeline. Runs in the background (~10 min). Check upload history for progress.</span>
                </span>
            </label>
        </div>

        <button type="submit" class="save" id="submitBtn" style="font-size:1rem;">
            🚀 Generate Now
        </button>
    </form>
</div>

<script>
document.getElementById('genForm').addEventListener('submit', function () {
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Asking Gemini… (~10 seconds)';
});
</script>

<?php include 'templates/footer.php'; ?>
