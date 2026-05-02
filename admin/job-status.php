<?php
require_once '../includes/db.php';
header('Content-Type: application/json; charset=utf-8');

$raw = $_GET['ids'] ?? '';
$ids = array_values(array_filter(array_map('intval', explode(',', $raw))));

if (empty($ids)) { echo '[]'; exit; }

$ph   = implode(',', array_fill(0, count($ids), '?'));
$stmt = $pdo->prepare("
    SELECT id, status, youtube_url, error_message, created_at, completed_at
    FROM video_jobs WHERE id IN ($ph)
");
$stmt->execute($ids);
echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
