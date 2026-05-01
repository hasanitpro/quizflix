<?php
$host = 'localhost';
$dbname = 'quizflix';
$username = 'root';       // Default XAMPP/MySQL user
$password = '';           // Empty password for local dev

try {
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8mb4", $username, $password);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    die("❌ Database connection failed: " . $e->getMessage());
}
?>