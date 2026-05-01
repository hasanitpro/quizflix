<?php
session_start();
require_once '../includes/db.php';
include 'templates/header.php';

// Fetch all quizzes
$stmt = $pdo->query("
  SELECT q.id, q.title, q.created_at, q.last_uploaded_at, COUNT(qq.id) as total_questions
  FROM quizzes q
  LEFT JOIN questions qq ON q.id = qq.quiz_id
  GROUP BY q.id
  ORDER BY q.created_at DESC
");
$quizzes = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Fetch recent video jobs
$jobsStmt = $pdo->query("
  SELECT vj.id, vj.status, vj.youtube_url, vj.error_message,
         vj.created_at, vj.completed_at, q.title as quiz_title
  FROM video_jobs vj
  JOIN quizzes q ON q.id = vj.quiz_id
  ORDER BY vj.created_at DESC
  LIMIT 10
");
$videoJobs = $jobsStmt->fetchAll(PDO::FETCH_ASSOC);
?>

<h1>📊 Quizflix Admin Dashboard</h1>

<?php if (isset($_SESSION['message'])): ?>
<div id="flash-message" style="
    background: #d4edda;
    color: #155724;
    padding: 12px 16px;
    border-radius: 6px;
    border: 1px solid #c3e6cb;
    margin-bottom: 20px;
    font-weight: 500;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
">
    <?= htmlspecialchars($_SESSION['message']) ?>
</div>
<script>
setTimeout(() => {
    const msg = document.getElementById('flash-message');
    if (msg) msg.style.display = 'none';
}, 4000);
</script>
<?php unset($_SESSION['message']); endif; ?>

<p>
    <a href="upload-csv.php" class="button">➕ Upload New Quiz (CSV)</a>
    <a href="create-quiz.php" class="button">➕ Add New Quiz Manually</a>
</p>

<?php if (count($quizzes) === 0): ?>
<p>No quizzes found.</p>
<?php else: ?>
<table>
    <thead>
        <tr>
            <th>Title</th>
            <th>Questions</th>
            <th>Created At</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        <?php foreach ($quizzes as $quiz): ?>
        <tr>
            <td><?= htmlspecialchars($quiz['title']) ?></td>
            <td><?= $quiz['total_questions'] ?></td>
            <td><?= date("Y-m-d H:i", strtotime($quiz['created_at'])) ?></td>
            <td class="actions">
                <a href="edit.php?id=<?= $quiz['id'] ?>" class="button">✏️ Edit</a>
                <a href="../index.php?id=<?= $quiz['id'] ?>&preview=true" class="button" target="_blank">👁 Preview</a>
                <a href="trigger-video.php?id=<?= $quiz['id'] ?>" class="button"
                    onclick="return confirm('Generate and upload this quiz to YouTube now?');">🎬 Upload to YouTube</a>
                <a href="delete-quiz.php?id=<?= $quiz['id'] ?>" class="button danger"
                    onclick="return confirm('Delete this quiz?');">🗑 Delete</a>
            </td>
        </tr>
        <?php endforeach ?>
    </tbody>
</table>
<?php endif; ?>

<h2 style="margin-top:40px;">🎬 Recent YouTube Uploads</h2>

<?php if (count($videoJobs) === 0): ?>
<p>No video jobs yet. Use the "Upload to YouTube" button on any quiz, or wait for the daily scheduled run.</p>
<?php else: ?>
<table>
    <thead>
        <tr>
            <th>Quiz</th>
            <th>Status</th>
            <th>YouTube Link</th>
            <th>Started</th>
            <th>Completed</th>
        </tr>
    </thead>
    <tbody>
        <?php foreach ($videoJobs as $job): ?>
        <tr>
            <td><?= htmlspecialchars($job['quiz_title']) ?></td>
            <td>
                <?php
                $statusMap = [
                    'done'       => '✅ Done',
                    'failed'     => '❌ Failed',
                    'generating' => '⏳ Generating',
                    'uploading'  => '⬆️ Uploading',
                    'pending'    => '🕐 Pending',
                ];
                echo $statusMap[$job['status']] ?? htmlspecialchars($job['status']);
                if ($job['status'] === 'failed' && $job['error_message']) {
                    echo '<br><small style="color:#c0392b">' . htmlspecialchars(substr($job['error_message'], 0, 100)) . '</small>';
                }
                ?>
            </td>
            <td>
                <?php if ($job['youtube_url']): ?>
                <a href="<?= htmlspecialchars($job['youtube_url']) ?>" target="_blank">▶ Watch</a>
                <?php else: ?>
                —
                <?php endif; ?>
            </td>
            <td><?= $job['created_at'] ? date("Y-m-d H:i", strtotime($job['created_at'])) : '—' ?></td>
            <td><?= $job['completed_at'] ? date("Y-m-d H:i", strtotime($job['completed_at'])) : '—' ?></td>
        </tr>
        <?php endforeach; ?>
    </tbody>
</table>
<?php endif; ?>

<?php include 'templates/footer.php'; ?>