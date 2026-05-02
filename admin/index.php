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

<h1>📊 AZ Quiz Hub Admin Dashboard</h1>

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
    <a href="generate-quiz.php" class="button" style="background:#9c27b0;">🤖 Generate AI Quiz</a>
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

<?php
$activeStatuses = ['pending', 'generating', 'uploading'];
$activeJobs     = array_filter($videoJobs, fn($j) => in_array($j['status'], $activeStatuses));

// Progress config per status (pct is the fallback when DB progress=0)
$progressCfg = [
    'pending'    => ['pct' =>  2, 'label' => 'Queued — waiting to start',  'color' => '#9e9e9e', 'pulse' => false],
    'generating' => ['pct' =>  5, 'label' => 'Starting…',                  'color' => '#2196F3', 'pulse' => true],
    'uploading'  => ['pct' => 99, 'label' => 'Uploading to YouTube…',      'color' => '#ff9800', 'pulse' => true],
    'done'       => ['pct' => 100,'label' => '✅ Done',                     'color' => '#4CAF50', 'pulse' => false],
    'failed'     => ['pct' => 100,'label' => '❌ Failed',                   'color' => '#f44336', 'pulse' => false],
];
?>

<!-- Active-jobs toast (fixed bottom-right; JS shows it when jobs are running) -->
<div class="active-jobs-banner" id="active-banner" style="display:none;">
    <div class="spinner"></div>
    <div>
        <strong id="banner-text">Video generation in progress…</strong>
        <div class="banner-sub">You can safely leave this page — the process runs in the background.</div>
    </div>
</div>

<h2 style="margin-top:40px;">🎬 Recent YouTube Uploads</h2>

<?php if (count($videoJobs) === 0): ?>
<p>No video jobs yet. Use the "Upload to YouTube" button on any quiz, or wait for the daily scheduled run.</p>
<?php else: ?>
<table>
    <thead>
        <tr>
            <th>Quiz</th>
            <th>Status &amp; Progress</th>
            <th>YouTube</th>
            <th>Started</th>
            <th>Completed</th>
        </tr>
    </thead>
    <tbody>
        <?php foreach ($videoJobs as $job):
            $cfg      = $progressCfg[$job['status']] ?? $progressCfg['pending'];
            $isActive = in_array($job['status'], $activeStatuses);
            // Use real DB progress when available, fall back to status default
            $pct      = ($job['progress'] > 0) ? (int)$job['progress'] : $cfg['pct'];
            $label    = ($job['progress_label'] !== null && $job['progress_label'] !== '')
                        ? $job['progress_label'] : $cfg['label'];
        ?>
        <tr data-job-id="<?= (int)$job['id'] ?>" data-status="<?= htmlspecialchars($job['status']) ?>">
            <td><?= htmlspecialchars($job['quiz_title']) ?></td>

            <td class="job-status-cell">
                <div class="progress-wrap">
                    <div class="progress-track">
                        <div class="progress-fill <?= $cfg['pulse'] ? 'pulsing' : '' ?>"
                             style="width:<?= $pct ?>%;background:<?= $cfg['color'] ?>"></div>
                    </div>
                    <div class="progress-label">
                        <?= htmlspecialchars($label) ?>
                        <?php if ($isActive && $pct > 0): ?>
                        <span class="progress-pct"><?= $pct ?>%</span>
                        <?php endif ?>
                    </div>
                </div>
                <?php if ($job['status'] === 'failed' && $job['error_message']): ?>
                <details style="margin-top:4px;">
                    <summary style="color:#c0392b;font-size:0.82rem;cursor:pointer;">
                        <?= htmlspecialchars(substr($job['error_message'], 0, 80)) ?>…
                    </summary>
                    <pre style="font-size:0.78rem;color:#c0392b;white-space:pre-wrap;margin:4px 0 0;"><?= htmlspecialchars($job['error_message']) ?></pre>
                </details>
                <?php endif ?>
            </td>

            <td>
                <?php if ($job['youtube_url']): ?>
                <a href="<?= htmlspecialchars($job['youtube_url']) ?>" target="_blank"
                   class="button" style="padding:4px 10px;">▶ Watch</a>
                <?php else: ?>
                —
                <?php endif ?>
            </td>

            <td><?= $job['created_at']   ? date("Y-m-d H:i", strtotime($job['created_at']))   : '—' ?></td>
            <td><?= $job['completed_at'] ? date("Y-m-d H:i", strtotime($job['completed_at'])) : '—' ?></td>
        </tr>
        <?php endforeach ?>
    </tbody>
</table>
<?php endif ?>

<script>
const ACTIVE   = ['pending', 'generating', 'uploading'];
const DEFAULTS = {
    pending:    { pct:  2, label: 'Queued — waiting to start', color: '#9e9e9e', pulse: false },
    generating: { pct:  5, label: 'Starting…',                 color: '#2196F3', pulse: true  },
    uploading:  { pct: 99, label: 'Uploading to YouTube…',     color: '#ff9800', pulse: true  },
    done:       { pct: 100,label: '✅ Done',                    color: '#4CAF50', pulse: false },
    failed:     { pct: 100,label: '❌ Failed',                  color: '#f44336', pulse: false },
};

function getActiveIds() {
    return [...document.querySelectorAll('tr[data-job-id]')]
        .filter(r => ACTIVE.includes(r.dataset.status))
        .map(r => r.dataset.jobId);
}

function renderStatus(cell, job) {
    const cfg  = DEFAULTS[job.status] || DEFAULTS.pending;
    // Use real DB progress when available, fall back to status default
    const pct  = (job.progress > 0) ? job.progress : cfg.pct;
    const lbl  = (job.progress_label) ? job.progress_label : cfg.label;
    const isActive = ACTIVE.includes(job.status);

    let html = `
        <div class="progress-wrap">
            <div class="progress-track">
                <div class="progress-fill ${cfg.pulse ? 'pulsing' : ''}"
                     style="width:${pct}%;background:${cfg.color}"></div>
            </div>
            <div class="progress-label">
                ${lbl}
                ${isActive && pct > 0 ? `<span class="progress-pct">${pct}%</span>` : ''}
            </div>
        </div>`;
    if (job.status === 'failed' && job.error_message)
        html += `<details style="margin-top:4px;"><summary style="color:#c0392b;font-size:0.82rem;cursor:pointer;">${job.error_message.substring(0,80)}…</summary><pre style="font-size:0.78rem;color:#c0392b;white-space:pre-wrap;margin:4px 0 0;">${job.error_message}</pre></details>`;
    if (job.status === 'done' && job.youtube_url)
        html += `<a href="${job.youtube_url}" target="_blank" class="button" style="margin-top:5px;padding:4px 10px;display:inline-block;">▶ Watch</a>`;
    cell.innerHTML = html;
}

function updateBanner(activeCount) {
    const banner = document.getElementById('active-banner');
    const text   = document.getElementById('banner-text');
    if (activeCount > 0) {
        banner.style.display = 'flex';
        text.textContent = activeCount === 1
            ? '1 video job in progress…'
            : `${activeCount} video jobs in progress…`;
    } else {
        banner.style.display = 'none';
    }
}

async function pollJobs() {
    const ids = getActiveIds();
    updateBanner(ids.length);
    if (!ids.length) { clearInterval(timer); return; }

    try {
        const res  = await fetch(`job-status.php?ids=${ids.join(',')}`);
        const jobs = await res.json();
        for (const job of jobs) {
            const row = document.querySelector(`tr[data-job-id="${job.id}"]`);
            if (!row) continue;
            row.dataset.status = job.status;
            renderStatus(row.querySelector('.job-status-cell'), job);
            // Reload the Watch link in the YouTube column too
            const ytCell = row.cells[2];
            if (job.status === 'done' && job.youtube_url) {
                ytCell.innerHTML = `<a href="${job.youtube_url}" target="_blank" class="button" style="padding:4px 10px;">▶ Watch</a>`;
            }
            // Reload the Completed column
            if (job.completed_at) {
                row.cells[4].textContent = job.completed_at.substring(0, 16);
            }
        }
        updateBanner(getActiveIds().length);
    } catch(e) { console.warn('Job poll failed:', e); }
}

// Kick off — poll immediately then every 5 s
pollJobs();
const timer = setInterval(pollJobs, 5000);
</script>

<?php include 'templates/footer.php'; ?>