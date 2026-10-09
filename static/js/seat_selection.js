document.addEventListener("DOMContentLoaded", () => {
  const seatButtons = document.querySelectorAll(".seat-btn:not([disabled])");
  const hiddenInput = document.getElementById("selected-seat-ids");
  const labelsSpan = document.getElementById("selected-seat-labels");
  const totalSpan = document.getElementById("selected-seat-total");
  const submitBtn = document.getElementById("proceed-checkout-btn");

  const selected = new Map();

  function updateSummary() {
    const ids = Array.from(selected.keys());
    const labels = Array.from(selected.values()).map((item) => item.label);
    const subtotal = Array.from(selected.values()).reduce(
      (acc, item) => acc + item.price,
      0
    );

    if (hiddenInput) hiddenInput.value = ids.join(",");
    if (labelsSpan) labelsSpan.textContent = labels.length ? labels.join(", ") : "None";
    if (totalSpan) totalSpan.textContent = subtotal.toFixed(2);
    if (submitBtn) submitBtn.disabled = ids.length === 0;
  }

  seatButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-seat-id");
      const label = btn.getAttribute("data-seat-label");
      const price = parseFloat(btn.getAttribute("data-seat-price") || "0");

      if (selected.has(id)) {
        selected.delete(id);
        btn.classList.remove("selected");
      } else {
        if (selected.size >= 10) {
          return;
        }
        selected.set(id, { label, price });
        btn.classList.add("selected");
      }
      updateSummary();
    });
  });
});
