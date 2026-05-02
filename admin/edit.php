<?php
require_once '../includes/db.php';
include 'templates/header.php';

$id = isset($_GET['id']) ? intval($_GET['id']) : 0;
$stmt = $pdo->prepare("SELECT * FROM quizzes WHERE id = ?");
$stmt->execute([$id]);
$quiz = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$quiz) die("Quiz not found.");

// Fetch all questions and options
$questionStmt = $pdo->prepare("SELECT * FROM questions WHERE quiz_id = ?");
$questionStmt->execute([$id]);
$questions = $questionStmt->fetchAll(PDO::FETCH_ASSOC);
$optionStmt = $pdo->prepare("SELECT * FROM options WHERE question_id = ?");
foreach ($questions as &$q) {
    $optionStmt->execute([$q['id']]);
    $q['options'] = $optionStmt->fetchAll(PDO::FETCH_ASSOC);
}

// Handle quiz meta save
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_quiz'])) {
    $stmt = $pdo->prepare("
        UPDATE quizzes SET
            title = ?, intro_text = ?, outro_text = ?,
            bg_music = ?, correct_sound = ?, background_image = ?
        WHERE id = ?
    ");
    $stmt->execute([
        $_POST['title'], $_POST['intro_text'], $_POST['outro_text'],
        $_POST['bg_music'], $_POST['correct_sound'], $_POST['background_image'],
        $id
    ]);
    header("Location: edit.php?id=$id&saved=1");
    exit;
}

// Handle question save
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_questions'])) {
    $pdo->beginTransaction();
    $pdo->prepare("DELETE FROM questions WHERE quiz_id = ?")->execute([$id]);

    foreach ($_POST['questions'] as $q) {
        $stmt = $pdo->prepare("INSERT INTO questions (quiz_id, question_text, correct_index, fun_fact) VALUES (?, ?, ?, ?)");
        $stmt->execute([$id, $q['text'], $q['correct'], $q['fun']]);
        $qid = $pdo->lastInsertId();

        foreach ($q['options'] as $i => $opt) {
            $stmt = $pdo->prepare("INSERT INTO options (question_id, option_index, option_text) VALUES (?, ?, ?)");
            $stmt->execute([$qid, $i, $opt]);
        }
    }
    $pdo->commit();
    header("Location: edit.php?id=$id&questions_updated=1");
    exit;
}

function listFiles($dir, $exts) {
    return array_values(array_filter(array_map('basename', glob("$dir/*")), function ($f) use ($exts) {
        return in_array(strtolower(pathinfo($f, PATHINFO_EXTENSION)), $exts);
    }));
}

$audioFiles = listFiles('../public/media', ['mp3']);
$imageFiles = listFiles('../public/media', ['jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4']);
?>

<a class="back-link" href="index.php">← Back to Dashboard</a>
<h2>Edit Quiz: <?= htmlspecialchars($quiz['title']) ?></h2>

<div class="tabs">
    <button class="tab-btn active" onclick="showTab('quiz')">🧩 Quiz Info</button>
    <button class="tab-btn" onclick="showTab('questions')">✏️ Questions</button>
</div>

<!-- Quiz Info Tab -->
<div class="tab active" id="quiz">
    <form method="post">
        <input type="hidden" name="save_quiz" value="1">
        <label>Title</label>
        <input type="text" name="title" value="<?= htmlspecialchars($quiz['title']) ?>" required>
        <label>Intro Text</label>
        <textarea name="intro_text"><?= htmlspecialchars($quiz['intro_text']) ?></textarea>
        <label>Outro Text</label>
        <textarea name="outro_text"><?= htmlspecialchars($quiz['outro_text']) ?></textarea>

        <?php
    $assets = [
      'bg_music'         => ['label' => 'Background Music',       'files' => $audioFiles],
      'correct_sound'    => ['label' => 'Correct Answer Sound',   'files' => $audioFiles],
      'background_image' => ['label' => 'Background Image/Video', 'files' => $imageFiles],
    ];

    foreach ($assets as $name => $info):
      $selected = $quiz[$name];
    ?>
        <label>
            <?= $info['label'] ?>
            <button type="button" class="upload-btn" onclick="openUploader('<?= $name ?>')">📤 Upload</button>
        </label>
        <select name="<?= $name ?>" onchange="updateAssetPreview('<?= $name ?>', this.value)">
            <option value="">-- None --</option>
            <?php foreach ($info['files'] as $f): ?>
            <option value="<?= $f ?>" <?= $f === $selected ? 'selected' : '' ?>><?= $f ?></option>
            <?php endforeach ?>
        </select>
        <div class="preview" id="<?= $name ?>_preview">
            <?php if ($selected): ?>
            <?php if ($name === 'background_image'):
            $ext = strtolower(pathinfo($selected, PATHINFO_EXTENSION));
            if ($ext === 'mp4'): ?>
            <video src="../public/media/<?= $selected ?>" autoplay muted loop playsinline
                style="max-height:100px;"></video>
            <?php else: ?>
            <img src="../public/media/<?= $selected ?>" style="max-height:100px;" />
            <?php endif ?>
            <?php else: ?>
            <audio controls src="../public/media/<?= $selected ?>"></audio>
            <?php endif ?>
            <?php endif ?>
        </div>
        <?php endforeach; ?>

        <button class="save" type="submit">💾 Save Quiz Info</button>
        <p style="margin-top: 1.5rem;">
            <a href="../index.php?id=<?= $quiz['id'] ?>&preview=true" target="_blank"
                style="text-decoration: none; background: #2196F3; color: white; padding: 0.6rem 1rem; border-radius: 6px;">
                👁 Preview This Quiz</a>
        </p>
    </form>
</div>

<!-- Questions Tab -->
<div class="tab" id="questions">
    <form method="post">
        <input type="hidden" name="save_questions" value="1">
        <table class="question-table" id="questionTable">
            <thead>
                <tr>
                    <th>Question</th>
                    <th>A</th>
                    <th>B</th>
                    <th>C</th>
                    <th>D</th>
                    <th>Correct</th>
                    <th>Fun Fact</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($questions as $i => $q): ?>
                <tr>
                    <td><input type="text" name="questions[<?= $i ?>][text]"
                            value="<?= htmlspecialchars($q['question_text']) ?>"></td>
                    <?php foreach ($q['options'] as $j => $opt): ?>
                    <td><input type="text" name="questions[<?= $i ?>][options][<?= $j ?>]"
                            value="<?= htmlspecialchars($opt['option_text']) ?>"></td>
                    <?php endforeach ?>
                    <td>
                        <select name="questions[<?= $i ?>][correct]">
                            <?php foreach (['A','B','C','D'] as $j => $label): ?>
                            <option value="<?= $j ?>" <?= $j == $q['correct_index'] ? 'selected' : '' ?>><?= $label ?>
                            </option>
                            <?php endforeach ?>
                        </select>
                    </td>
                    <td><textarea name="questions[<?= $i ?>][fun]"><?= htmlspecialchars($q['fun_fact']) ?></textarea>
                    </td>
                    <td><button type="button" class="remove-btn" onclick="this.closest('tr').remove()">🗑</button></td>
                </tr>
                <?php endforeach ?>
            </tbody>
        </table>
        <button type="button" class="add-btn" onclick="addQuestionRow()">➕ Add Question</button><br>
        <button class="save" type="submit">💾 Save Questions</button>
    </form>
</div>

<script>
const quizId = <?= json_encode($quiz['id']) ?>;

function showTab(tab) {
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(tab).classList.add('active');
    event.target.classList.add('active');
}

function updateAssetPreview(name, filename) {
    const preview = document.getElementById(`${name}_preview`);
    if (!preview) return;
    if (!filename) return preview.innerHTML = '';
    const path = `../public/media/${filename}`;
    const ext = filename.split('.').pop().toLowerCase();
    if (name === 'background_image') {
        if (ext === 'mp4') {
            preview.innerHTML =
                `<video src="${path}" autoplay muted loop playsinline style="max-height:100px;"></video>`;
        } else {
            preview.innerHTML = `<img src="${path}" style="max-height:100px;" />`;
        }
    } else {
        preview.innerHTML = `<audio controls src="${path}"></audio>`;
    }
}

function openUploader(target) {
    const popup = window.open(`upload-assets.php?quiz=${quizId}&target=${target}`, 'uploadWin', 'width=500,height=400');
    popup.focus();
}

window.addEventListener("message", (e) => {
    const {
        filename,
        target
    } = e.data || {};
    if (!filename || !target) return;
    const select = document.querySelector(`select[name="${target}"]`);
    if (!select) return;
    if (![...select.options].some(opt => opt.value === filename)) {
        const opt = new Option(filename, filename);
        select.appendChild(opt);
    }
    select.value = filename;
    updateAssetPreview(target, filename);
});

let questionCount = <?= count($questions) ?>;

function addQuestionRow() {
    const table = document.getElementById("questionTable").querySelector("tbody");
    const i = questionCount++;
    const row = document.createElement("tr");
    row.innerHTML = `
    <td><input type="text" name="questions[${i}][text]"></td>
    <td><input type="text" name="questions[${i}][options][0]"></td>
    <td><input type="text" name="questions[${i}][options][1]"></td>
    <td><input type="text" name="questions[${i}][options][2]"></td>
    <td><input type="text" name="questions[${i}][options][3]"></td>
    <td>
      <select name="questions[${i}][correct]">
        <option value="0">A</option><option value="1">B</option>
        <option value="2">C</option><option value="3">D</option>
      </select>
    </td>
    <td><textarea name="questions[${i}][fun]"></textarea></td>
    <td><button type="button" class="remove-btn" onclick="this.closest('tr').remove()">🗑</button></td>
  `;
    table.appendChild(row);
}
</script>

<?php include 'templates/footer.php'; ?>