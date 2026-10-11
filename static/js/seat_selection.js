document.addEventListener("DOMContentLoaded", () => {
  const seatButtons = document.querySelectorAll(".seat-btn");
  const hiddenInput = document.getElementById("selected-seat-ids");
  const labelsSpan = document.getElementById("selected-seat-labels");
  const totalSpan = document.getElementById("selected-seat-total");
  const submitBtn = document.getElementById("proceed-checkout-btn");
  const availabilityStatus = document.getElementById("availability-status");
  const availabilityUrl = window.movieShowAvailabilityUrl;

  const selected = new Map();
  seatButtons.forEach((btn) => {
    if (btn.classList.contains("selected")) {
      selected.set(btn.dataset.seatId, {
        label: btn.dataset.seatLabel,
        price: Number.parseFloat(btn.dataset.seatPrice || "0")
      });
    }
  });
  updateSummary();

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
      const heldByCurrentBooking = btn.dataset.heldByCurrentBooking === "true";
      if (btn.disabled || (btn.dataset.status !== "available" && !heldByCurrentBooking)) return;
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

    async function refreshAvailability() {
      try {
        const response = await fetch(availabilityUrl, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          cache: "no-store"
        });
        if (!response.ok) throw new Error(`Availability request failed (${response.status}).`);
        const data = await response.json();
        data.seats.forEach((seat) => {
          const button = document.querySelector(`[data-seat-id="${seat.id}"]`);
          if (!button) return;
          button.dataset.status = seat.status;
          button.dataset.seatPrice = seat.price;
          button.dataset.heldByCurrentBooking = String(seat.held_by_current_booking);
          const available = seat.status === "available" || seat.held_by_current_booking;
          if (!available && selected.has(String(seat.id))) {
            selected.delete(String(seat.id));
            button.classList.remove("selected");
            updateSummary();
          }
          button.disabled = !available;
          button.setAttribute("aria-disabled", String(!available));
          button.classList.toggle("btn-outline-light", available);
          button.classList.toggle("btn-warning", seat.status === "held");
          button.classList.toggle("btn-danger", seat.status === "booked");
          button.classList.toggle("selected", selected.has(String(seat.id)));
          button.classList.toggle("btn-secondary", seat.status !== "available" && seat.status !== "held" && seat.status !== "booked");
        });
        if (availabilityStatus) availabilityStatus.textContent = "Seat availability is up to date.";
      } catch (error) {
        if (availabilityStatus) availabilityStatus.textContent = "Unable to refresh availability; the server will verify seats before reserving.";
        console.error(error);
      }
    }

    if (availabilityUrl) {
      refreshAvailability();
      window.setInterval(refreshAvailability, 15000);
    }
  });
});
