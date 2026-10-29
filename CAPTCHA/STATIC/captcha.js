(() => {
  "use strict";

  const challenge = document.querySelector("#challenge");
  const buttons = [...document.querySelectorAll("button[data-shape]")];
  const progress = document.querySelector("#progress");
  const message = document.querySelector("#message");
  const sequence = challenge.dataset.sequence.split(",");
  const answers = [];

  async function submitAnswer() {
    message.textContent = "";
    try {
      const response = await fetch("/captcha/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          challenge_id: challenge.dataset.challengeId,
          answers,
        }),
      });
      const result = await response.json();
      if (result.status === "try_again" || result.status === "incorrect") {
        answers.length = 0;
        buttons.forEach((button) => { button.disabled = false; });
        progress.textContent = "0 of 3 selected";
        message.textContent = result.message || "That sequence did not match. Try again.";
        return;
      }
      if (!response.ok || result.status !== "verified") {
        message.textContent = "That sequence did not match. Please start a new check.";
        return;
      }
      window.location.assign(result.redirect);
    } catch {
      message.textContent = "Verification is temporarily unavailable. Please try again.";
    }
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      if (answers.length >= sequence.length) return;
      answers.push(button.dataset.shape);
      button.disabled = true;
      progress.textContent = `${answers.length} of ${sequence.length} selected`;
      if (answers.length === sequence.length) submitAnswer();
    });
  });
})();
