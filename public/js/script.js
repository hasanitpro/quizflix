const urlParams   = new URLSearchParams(window.location.search);
const quizId      = urlParams.get("id");
const previewMode = urlParams.get("preview") === "true";

const quizSelector    = document.getElementById("quiz-selector");
const quizContainer   = document.getElementById("quiz");
const music           = document.getElementById("bg-music");
const chime           = document.getElementById("correct-chime");
const startBtn        = document.getElementById("start-btn");
const fullscreenBtn   = document.getElementById("fullscreen-btn");
const countdownOverlay = document.getElementById("countdown-overlay");
const countdownText   = document.getElementById("countdown");
const progressBar     = document.getElementById("quiz-progress");
const progressFill    = document.getElementById("progress-fill");
const progressLabel   = document.getElementById("progress-label");
const scoreBadge      = document.getElementById("quiz-score");
const scoreValue      = document.getElementById("score-value");
const scoreTotal      = document.getElementById("score-total");

let currentIndex  = -1;
let score         = 0;
let selectedVoice = null;
let quizData      = [];
let quizMeta      = {};
let pendingStream = null;
let mediaRecorder = null;

// ── Background ──────────────────────────────────────────────────────────────
function applyBackground(bgFile) {
    const ext      = bgFile?.split('.').pop()?.toLowerCase();
    const existing = document.getElementById("bg-video");
    if (existing) existing.remove();

    if (ext === "mp4") {
        const video = document.createElement("video");
        video.src         = `public/media/${bgFile}`;
        video.autoplay    = true;
        video.muted       = true;
        video.loop        = true;
        video.playsInline = true;
        video.id          = "bg-video";
        Object.assign(video.style, {
            position: "fixed", top: 0, left: 0,
            width: "100%", height: "100%",
            objectFit: "cover", zIndex: "-1",
        });
        document.body.appendChild(video);
        document.body.style.backgroundImage = "none";
    } else if (["gif", "jpg", "jpeg", "png", "webp"].includes(ext)) {
        document.body.style.backgroundImage = `url('public/media/${bgFile}')`;
        document.body.style.backgroundSize  = "cover";
        document.body.style.backgroundPosition = "center";
    }
}

function applyAudioFromQuizMeta(meta) {
    if (meta.bgMusic)      music.src = `public/media/${meta.bgMusic}`;
    if (meta.correctSound) chime.src = `public/media/${meta.correctSound}`;
}

// ── Visibility ───────────────────────────────────────────────────────────────
if (previewMode || quizId) {
    quizContainer.classList.remove("hidden");
} else {
    quizSelector.classList.remove("hidden");
}

// ── Voice ────────────────────────────────────────────────────────────────────
function loadVoices() {
    const voices = speechSynthesis.getVoices();
    selectedVoice = voices.find(v =>
        v.name.includes("Google") || v.name.includes("Microsoft") || v.lang === "en-US"
    ) || voices[0];
}
speechSynthesis.onvoiceschanged = loadVoices;
loadVoices();

// ── Quiz start ───────────────────────────────────────────────────────────────
function startQuiz() {
    music.volume = 0.3;
    music.play().catch(console.warn);
    if (startBtn) startBtn.style.display = "none";

    // Show score badge
    scoreBadge.classList.remove("hidden");
    scoreTotal.textContent = quizData.length;
    scoreValue.textContent = 0;

    speak(quizMeta.introText || "Welcome to AZ Quiz Hub!", () => setTimeout(showQuestion, 800));
}

// ── Selector ─────────────────────────────────────────────────────────────────
if (!previewMode && !quizId) {
    fetch("./api/get-quizzes.php")
        .then(r => r.json())
        .then(data => {
            const dropdown = document.getElementById("quiz-dropdown");
            data.forEach(q => {
                const opt = document.createElement("option");
                opt.value       = q.id;
                opt.textContent = q.title;
                dropdown.appendChild(opt);
            });
        });

    document.getElementById("load-quiz-btn").addEventListener("click", () => {
        const id = document.getElementById("quiz-dropdown").value;
        if (!id || id === "-- Choose a Quiz --") return;
        window.location.href = `${window.location.origin}${window.location.pathname}?id=${id}`;
    });
}

// ── Load quiz data ────────────────────────────────────────────────────────────
if (quizId) {
    fetch(`./api/get-quiz.php?id=${quizId}`)
        .then(r => r.json())
        .then(data => {
            quizMeta = data;
            quizData = data.questions;
            applyAudioFromQuizMeta(quizMeta);
            if (quizMeta.backgroundImage) applyBackground(quizMeta.backgroundImage);
            if (previewMode) setTimeout(startQuiz, 200);
        })
        .catch(() => { quizContainer.innerHTML = "<p>Error loading quiz.</p>"; });
}

// ── Show question ─────────────────────────────────────────────────────────────
function showQuestion() {
    transition(() => {
        currentIndex++;
        if (currentIndex >= quizData.length) { showOutro(); return; }

        const q      = quizData[currentIndex];
        const labels = ["A", "B", "C", "D"];
        const cls    = ["opt-a", "opt-b", "opt-c", "opt-d"];

        const optionsHtml = q.o.map((opt, i) => `
            <div class="option ${cls[i]}" data-index="${i}">
                <span class="opt-letter">${labels[i]}</span>
                <span class="opt-text">${opt}</span>
            </div>`).join("");

        quizContainer.innerHTML = `
            <div class="question-box">
                <div class="question-meta">Question ${currentIndex + 1} of ${quizData.length}</div>
                <div class="question" id="typed-question"></div>
                <div class="options">${optionsHtml}</div>
                <div class="circle-timer">
                    <svg viewBox="0 0 100 100">
                        <circle r="45" cx="50" cy="50" class="bg"></circle>
                        <circle r="45" cx="50" cy="50" class="fg" id="circle-progress"></circle>
                        <text x="50%" y="55%" text-anchor="middle" class="timer-text" id="timer">10</text>
                    </svg>
                </div>
            </div>`;

        // Progress bar
        progressBar.classList.remove("hidden");
        progressLabel.textContent = `Question ${currentIndex + 1} of ${quizData.length}`;
        progressFill.style.width  = `${(currentIndex / quizData.length) * 100}%`;

        const questionEl = document.getElementById("typed-question");
        typeText(q.q, questionEl, () => {
            speak(q.q, () => startTimer(q));
        });
    });
}

// ── Timer ────────────────────────────────────────────────────────────────────��
function startTimer(q) {
    let time        = 10;
    const timerEl   = document.getElementById("timer");
    const progressEl = document.getElementById("circle-progress");
    const totalDash  = 283;

    progressEl.style.strokeDashoffset = 0;
    timerEl.textContent = "10";

    const interval = setInterval(() => {
        time--;
        timerEl.textContent = time;
        progressEl.style.strokeDashoffset = totalDash - (time / 10) * totalDash;

        // Colour urgency
        if (time <= 2) {
            progressEl.setAttribute("data-urgent", "2");
        } else if (time <= 5) {
            progressEl.setAttribute("data-urgent", "1");
        }

        if (time <= 0) {
            clearInterval(interval);
            revealAnswer(q);
        }
    }, 1000);
}

function revealAnswer(q) {
    const options     = document.querySelectorAll(".option");
    const correctOpt  = options[q.c];
    if (correctOpt) {
        correctOpt.classList.add("correct");
        score++;
        scoreValue.textContent = score;
    }
    chime.play();

    // Fill progress to current question
    progressFill.style.width = `${((currentIndex + 1) / quizData.length) * 100}%`;

    speak(q.f || "", () => setTimeout(showQuestion, 800));
}

// ── Outro ─────────────────────────────────────────────────────────────────────
function showOutro() {
    progressBar.classList.add("hidden");
    const text = quizMeta.outroText || "Thanks for playing!";
    speak(text);
    quizContainer.innerHTML = `
        <div class="outro-screen">
            <h2>🎉 Quiz Complete!</h2>
            <p>You scored <strong>${score} out of ${quizData.length}</strong>.</p>
            <p style="margin-top:0.8rem">${text.replace(/\n/g, "<br/>")}</p>
        </div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function transition(callback) {
    quizContainer.style.opacity = "0";
    quizContainer.style.transform = "translateY(16px)";
    quizContainer.style.transition = "opacity 0.18s ease, transform 0.18s ease";
    setTimeout(() => {
        callback();
        quizContainer.style.opacity   = "1";
        quizContainer.style.transform = "translateY(0)";
    }, 180);
}

function typeText(text, element, callback, speed = 55) {
    let i = 0;
    element.innerHTML = "";
    const typing = setInterval(() => {
        element.innerHTML += text.charAt(i++);
        if (i >= text.length) { clearInterval(typing); callback?.(); }
    }, speed);
}

function speak(text, onEnd) {
    if (!window.speechSynthesis) return onEnd?.();
    window.speechSynthesis.cancel();
    const msg = new SpeechSynthesisUtterance(text);
    if (selectedVoice) msg.voice = selectedVoice;
    msg.rate   = 0.92;
    msg.pitch  = 1;
    msg.volume = 1;
    msg.onend  = () => onEnd?.();
    speechSynthesis.speak(msg);
}

// ── Screen recording flow ─────────────────────────────────────────────────────
startBtn?.addEventListener("click", async () => {
    startBtn.style.display = "none";
    try {
        pendingStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
        fullscreenBtn.style.display = "block";
    } catch {
        startQuiz();
    }
});

fullscreenBtn?.addEventListener("click", async () => {
    fullscreenBtn.style.display = "none";
    try { await document.documentElement.requestFullscreen(); } catch {}

    countdownOverlay.style.display = "flex";
    let cd = 5;
    countdownText.textContent = cd;

    const timer = setInterval(() => {
        countdownText.textContent = --cd;
        if (cd <= 0) {
            clearInterval(timer);
            countdownOverlay.style.display = "none";

            if (pendingStream) {
                mediaRecorder = new MediaRecorder(pendingStream);
                const chunks  = [];
                mediaRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
                mediaRecorder.onstop = () => {
                    const blob = new Blob(chunks, { type: "video/webm" });
                    const a = Object.assign(document.createElement("a"), {
                        href: URL.createObjectURL(blob), download: "quiz-recording.webm",
                    });
                    a.click();
                };
                mediaRecorder.start();
            }

            const origShowOutro = showOutro;
            showOutro = function () {
                origShowOutro();
                setTimeout(() => {
                    if (mediaRecorder?.state === "recording") mediaRecorder.stop();
                }, 2000);
            };

            startQuiz();
        }
    }, 1000);
});
