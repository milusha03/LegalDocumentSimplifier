const docInput = document.getElementById("docInput");
const removeBtn = document.getElementById("removeBtn");
const viewBtn = document.getElementById("viewBtn");
const simplifyBtn = document.getElementById("simplifyBtn");
const simplifyStatus = document.getElementById("simplifyStatus");
const spinner = document.getElementById("spinner");
const reviewForm = document.getElementById("reviewForm");
const toast = document.getElementById("toast");

// File validation and button enabling
docInput.addEventListener("change", () => {
  const file = docInput.files[0];

  if (!file || file.type !== "application/pdf") {
    alert("Only PDF files are allowed.");
    docInput.value = "";
    viewBtn.disabled = true;
    simplifyBtn.disabled = true;
    removeBtn.disabled = true;
    return;
  }

  viewBtn.disabled = false;
  simplifyBtn.disabled = false;
  removeBtn.disabled = false;
});

// Remove file
removeBtn.addEventListener("click", () => {
  docInput.value = "";
  viewBtn.disabled = true;
  simplifyBtn.disabled = true;
  removeBtn.disabled = true;
});

// View PDF
viewBtn.addEventListener("click", () => {
  const file = docInput.files[0];
  if (file && file.type === "application/pdf") {
    const fileURL = URL.createObjectURL(file);
    window.open(fileURL, "_blank");
  }
});

// Simplify PDF
simplifyBtn.addEventListener("click", () => {
  simplifyStatus.classList.remove("hidden");
  spinner.classList.remove("hidden");

  // Disable all buttons during processing
  docInput.disabled = true;
  removeBtn.disabled = true;
  viewBtn.disabled = true;
  simplifyBtn.disabled = true;

  const file = docInput.files[0];
  if (!file || file.type !== "application/pdf") {
    alert("Please upload a valid PDF file.");
    spinner.classList.add("hidden");
    simplifyStatus.classList.add("hidden");
    docInput.disabled = false;
    removeBtn.disabled = false;
    return;
  }

  const formData = new FormData();
  formData.append("document", file);

  fetch("/submit_document", {
    method: "POST",
    body: formData
  })
    .then(response => {
      if (response.redirected) {
        window.location.href = response.url;
      } else {
        console.error("Simplification failed:", response.status);
        spinner.classList.add("hidden");
        simplifyStatus.classList.add("hidden");
        docInput.disabled = false;
        removeBtn.disabled = false;
      }
    })
    .catch(err => {
      console.error("Network error:", err);
      spinner.classList.add("hidden");
      simplifyStatus.classList.add("hidden");
      docInput.disabled = false;
      removeBtn.disabled = false;
    });
});

// Review submission (if present)
if (reviewForm) {
  reviewForm.addEventListener("submit", (e) => {
    e.preventDefault();

    const formData = new FormData(reviewForm);
    fetch("/submit_review", {
      method: "POST",
      body: formData
    }).then(response => {
      if (response.redirected) {
        toast.classList.add("show");
        setTimeout(() => {
          toast.classList.remove("show");
          window.location.href = response.url;
        }, 2000);
      }
    });
  });
}

function handleLogout() {
  fetch("/logout", {
    method: "POST",
    credentials: "include"
  })
  .then(() => {
    window.location.href = "/login";
  })
  .catch(err => {
    console.error("Logout failed:", err);
    alert("Something went wrong while logging out.");
  });
}
