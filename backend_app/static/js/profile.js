document.addEventListener("DOMContentLoaded", function () {
  const sendOtpBtn = document.getElementById("send-otp-btn");
  const otpSection = document.getElementById("otp-section");
  const updatePasswordBtn = document.getElementById("update-password-btn");

  sendOtpBtn.addEventListener("click", async () => {
    const email = document.getElementById("email").textContent;
    const res = await fetch("/send_password_otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        email,
        new_password: newPassword,
        confirm_password: confirmPassword
      }),
    });
    const data = await res.json();
    if (data.success) otpSection.style.display = "block";
    else alert("OTP failed: " + data.message);
  });

  updatePasswordBtn.addEventListener("click", async () => {
  const newPass = document.getElementById("new-password").value;
  const confirmPass = document.getElementById("confirm-password").value;
  const otp = document.getElementById("otp-code").value;

  if (newPass !== confirmPass) return alert("Passwords do not match.");

  const res = await fetch("/verify_password_otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ otp, new_password: newPass }),
  });

  const data = await res.json();

  if (data.success) {
    alert(data.message || "Password updated successfully!");
    setTimeout(() => {
      window.location.reload();
    }, 1000); // Delay for UX polish
  } else {
    alert(data.message || "Password update failed.");
  }
});
});

document.getElementById("send-otp-btn").addEventListener("click", async () => {
  const newPassword = document.getElementById("new-password").value;
  const confirmPassword = document.getElementById("confirm-password").value;
  const email = document.getElementById("email").textContent;
  const errorMessage = document.getElementById("error-message");

  if (!newPassword || !confirmPassword) {
    errorMessage.textContent = "Both password fields are required.";
    return;
  }

  if (newPassword !== confirmPassword) {
    errorMessage.textContent = "Passwords do not match.";
    return;
  }

  errorMessage.textContent = "";

  const response = await fetch("/send_password_otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      new_password: newPassword,
      confirm_password: confirmPassword
    })
  });

  const result = await response.json();
  if (result.success) {
    document.getElementById("otp-section").style.display = "block";
  } else {
    errorMessage.textContent = result.message;
  }
});


