// Rende ridimensionabili le colonne di ogni tabella con classe "admin-table"
// dentro un contenitore ".admin-table-wrap". Aggiunge una piccola maniglia
// trascinabile sul bordo destro di ogni intestazione.
(function () {
  function rendiRidimensionabile(table) {
    var headers = table.querySelectorAll("th");
    headers.forEach(function (th) {
      if (th.querySelector(".col-resizer")) return; // già fatto
      var handle = document.createElement("span");
      handle.className = "col-resizer";
      th.appendChild(handle);

      var startX, startWidth;

      handle.addEventListener("mousedown", function (e) {
        startX = e.pageX;
        startWidth = th.offsetWidth;
        handle.classList.add("resizing");
        document.body.style.userSelect = "none";

        function onMouseMove(e) {
          var newWidth = Math.max(60, startWidth + (e.pageX - startX));
          th.style.width = newWidth + "px";
        }
        function onMouseUp() {
          handle.classList.remove("resizing");
          document.body.style.userSelect = "";
          document.removeEventListener("mousemove", onMouseMove);
          document.removeEventListener("mouseup", onMouseUp);
        }
        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
        e.preventDefault();
      });

      // Supporto touch (tablet)
      handle.addEventListener("touchstart", function (e) {
        var touch = e.touches[0];
        startX = touch.pageX;
        startWidth = th.offsetWidth;
        handle.classList.add("resizing");

        function onTouchMove(e) {
          var t = e.touches[0];
          var newWidth = Math.max(60, startWidth + (t.pageX - startX));
          th.style.width = newWidth + "px";
        }
        function onTouchEnd() {
          handle.classList.remove("resizing");
          document.removeEventListener("touchmove", onTouchMove);
          document.removeEventListener("touchend", onTouchEnd);
        }
        document.addEventListener("touchmove", onTouchMove, { passive: true });
        document.addEventListener("touchend", onTouchEnd);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".admin-table-wrap .admin-table").forEach(rendiRidimensionabile);
  });
})();
