document.addEventListener("DOMContentLoaded", () => {
  const checkbox = document.getElementById("agreeCheckbox");
  const button = document.getElementById("continueBtn");

  checkbox.addEventListener("change", () => {
    button.disabled = !checkbox.checked;
  });
});


fetch("/accept_agreement", {
  method: "POST",
  body: JSON.stringify(data),
  headers: { "Content-Type": "application/json" }
})
.then(response => {
  if (response.redirected) {
    window.location.href = response.url;
  }
});

document.getElementById("agree-btn").addEventListener("click", () => {
  fetch("/accept_agreement", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accepted: true })
  })
  .then(response => {
    if (response.redirected) {
      window.location.href = response.url;
    }
  });
});

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
