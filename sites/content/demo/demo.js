/* UX-001: A local, deterministic interaction. No API calls, tracking or storage. */
(() => {
  "use strict";

  const ORIGINAL =
    "A fixed schedule reduces daily decisions and increases focus.";
  const REVISED =
    "A structured day reduces decision fatigue, while leaving flexible time helps adapt to the unexpected.";
  const STEPS = [
    "An original thought, recorded in August.",
    "A new note adds an important constraint.",
    "Two notes connect to the same knowledge node.",
    "A possible revision is proposed, not applied.",
    "Review the original sources before deciding.",
    "Choose whether to update your knowledge."
  ];
  const model = {
    step: 0,
    evidenceViewed: false,
    evidenceOpen: false,
    decision: "pending"
  };

  const root = document.getElementById("demo-app");
  if (!root) return;

  const byId = (id) => document.getElementById(id);
  const scenes = [...root.querySelectorAll("[data-scene]")];
  const progressSteps = [...root.querySelectorAll("[data-progress-step]")];
  const headings = scenes.map((scene) => scene.querySelector("h3"));
  const prev = byId("previous-step");
  const next = byId("next-step");
  const fraction = byId("step-fraction");
  const fill = byId("progress-fill");
  const hint = byId("next-hint");
  const announcer = byId("status-announcement");
  const evidence = byId("evidence-panel");
  const reviewButtons = [byId("review-sources"), byId("review-on-final")];
  const reviewedIndicator = byId("reviewed-indicator");
  const approve = byId("approve-revision");
  const reject = byId("reject-revision");
  const undo = byId("undo-decision");
  const decisionActions = byId("decision-actions");
  const outcome = byId("decision-outcome");
  const outcomeSymbol = byId("outcome-symbol");
  const outcomeTitle = byId("outcome-title");
  const outcomeDescription = byId("outcome-description");
  const node = root.querySelector(".knowledge-card");
  const nodeBody = byId("knowledge-text");
  const nodeStatus = byId("node-status");
  const nodeVersion = byId("knowledge-version");
  const sourceCount = byId("source-count");

  const announce = (message) => {
    announcer.textContent = message;
  };

  const render = ({ focus = false } = {}) => {
    root.dataset.step = String(model.step);
    root.dataset.reviewed = String(model.evidenceViewed);
    root.dataset.decision = model.decision;

    for (let index = 0; index < scenes.length; index += 1) {
      scenes[index].hidden = index !== model.step;
      progressSteps[index].classList.toggle("is-current", index === model.step);
      progressSteps[index].classList.toggle("is-complete", index < model.step);
      if (index === model.step) {
        progressSteps[index].setAttribute("aria-current", "step");
      } else {
        progressSteps[index].removeAttribute("aria-current");
      }
    }
    fraction.textContent = `${String(model.step + 1).padStart(2, "0")} / 06`;
    fill.style.width = `${((model.step + 1) / STEPS.length) * 100}%`;
    prev.disabled = model.step === 0;
    next.hidden = model.step === STEPS.length - 1;
    const reviewRequired = model.step === 4 && !model.evidenceViewed;
    next.disabled = reviewRequired;
    hint.textContent = reviewRequired ? "Inspect both sources to continue" : "";

    evidence.hidden = !model.evidenceOpen;
    reviewButtons.forEach((button) => {
      button.setAttribute("aria-expanded", String(model.evidenceOpen));
    });
    reviewedIndicator.textContent = model.evidenceViewed
      ? "✓ Both source excerpts reviewed"
      : "Required before you can approve";

    const decided = model.decision !== "pending";
    decisionActions.hidden = decided;
    outcome.hidden = !decided;
    undo.hidden = !decided;
    approve.disabled = model.decision !== "pending" || !model.evidenceViewed;
    if (decided) {
      outcome.classList.toggle("is-rejected", model.decision === "rejected");
      if (model.decision === "approved") {
        outcomeSymbol.textContent = "✓";
        outcomeTitle.textContent = "Your knowledge has evolved.";
        outcomeDescription.textContent =
          "The proposed revision now appears in the knowledge node. You can undo it at any time.";
      } else {
        outcomeSymbol.textContent = "↶";
        outcomeTitle.textContent = "You kept your original idea.";
        outcomeDescription.textContent =
          "The suggestion was rejected. Your knowledge node remains unchanged.";
      }
    }

    const approved = model.decision === "approved";
    node.classList.toggle("is-approved", approved);
    node.classList.toggle("is-rejected", model.decision === "rejected");
    nodeBody.textContent = approved ? REVISED : ORIGINAL;
    nodeStatus.textContent = approved ? "APPROVED REVISION" : "ORIGINAL IDEA";
    nodeVersion.textContent = approved ? "REVISION 02 · OCT 28" : "REVISION 01 · AUG 12";
    sourceCount.textContent = approved ? "2 SOURCES" : "1 SOURCE";

    if (focus) {
      headings[model.step].focus({ preventScroll: true });
    }
  };

  const goTo = (step) => {
    if (!Number.isInteger(step) || step < 0 || step >= STEPS.length) return;
    // The user must inspect source excerpts before the decision step.
    if (step > 4 && !model.evidenceViewed) {
      model.step = 4;
      render({ focus: true });
      announce("Please inspect both sources before continuing.");
      return;
    }
    model.step = step;
    render({ focus: true });
    announce(`Step ${step + 1} of 6. ${STEPS[step]}`);
  };

  const openEvidence = () => {
    model.evidenceViewed = true;
    model.evidenceOpen = true;
    render();
    evidence.scrollIntoView({ block: "nearest", behavior: "auto" });
    announce("Evidence opened. Both synthetic source excerpts are now visible.");
  };

  prev.addEventListener("click", () => goTo(model.step - 1));
  next.addEventListener("click", () => {
    if (model.step === 4 && !model.evidenceViewed) {
      announce("You must inspect the source evidence to continue.");
      return;
    }
    goTo(model.step + 1);
  });
  reviewButtons.forEach((button) => button.addEventListener("click", openEvidence));

  approve.addEventListener("click", () => {
    if (model.step !== 5 || !model.evidenceViewed || model.decision !== "pending") {
      announce("Review the sources and reach the final step before approving.");
      return;
    }
    model.decision = "approved";
    render();
    announce("Revision approved. Your knowledge node now shows the revised idea.");
  });

  reject.addEventListener("click", () => {
    if (model.step !== 5 || model.decision !== "pending") return;
    model.decision = "rejected";
    render();
    announce("Suggestion rejected. Your original knowledge remains unchanged.");
  });

  undo.addEventListener("click", () => {
    if (model.decision === "pending") return;
    model.decision = "pending";
    render();
    approve.focus();
    announce("Decision undone. The original knowledge has been restored.");
  });

  byId("reset-demo").addEventListener("click", () => {
    model.step = 0;
    model.evidenceViewed = false;
    model.evidenceOpen = false;
    model.decision = "pending";
    render({ focus: true });
    announce("Demo reset. You are back at the original idea.");
  });

  byId("start-demo").addEventListener("click", () => {
    headings[model.step].focus({ preventScroll: true });
  });

  render();
})();
