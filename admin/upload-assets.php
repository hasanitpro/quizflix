<?php
$uploadDir = '../public/media/';
$allowedTypes = [
  'audio/mpeg',
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
  'video/mp4'
];

$message = "";
$redirectId = isset($_GET['quiz']) ? intval($_GET['quiz']) : null;

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES['asset'])) {
  $file = $_FILES['asset'];
  $fileName = basename($file['name']);
  $fileType = mime_content_type($file['tmp_name']);

  if (in_array($fileType, $allowedTypes)) {
    $ext = pathinfo($fileName, PATHINFO_EXTENSION);
    $safeName = uniqid('asset_') . '.' . $ext;
    $targetPath = $uploadDir . $safeName;

    if (move_uploaded_file($file['tmp_name'], $targetPath)) {
      $message = "Upload successful: $safeName";
      echo "<script>
        if (window.opener) {
          window.opener.postMessage({ filename: '$safeName', target: '{$_GET['target']}' }, '*');
          window.close();
        }
      </script>";
    } else {
      $message = "Failed to move uploaded file.";
    }
  } else {
    $message = "Unsupported file type: $fileType";
  }
}
?>

<?php include 'templates/header.php'; ?>

<h2>📁 Upload Asset File</h2>

<form method="POST" enctype="multipart/form-data">
    <input type="file" name="asset" required>
    <br /><br />
    <button type="submit" class="save">Upload</button>
</form>

<?php if ($message): ?>
<p class="message"><?= htmlspecialchars($message) ?></p>
<?php endif; ?>

<?php include 'templates/footer.php'; ?>