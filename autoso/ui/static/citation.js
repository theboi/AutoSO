// autoso/ui/static/citation.js

let _activeRef = null;
let _activeCard = null;

/**
 * Highlight a citation card in the right panel and mark the clicked [N] span.
 * @param {number} citationNumber
 */
function highlightCitation(citationNumber) {
  if (_activeRef)  _activeRef.classList.remove("active");
  if (_activeCard) _activeCard.classList.remove("highlighted");

  const refs = document.querySelectorAll(
    `.citation-ref[data-citation="${citationNumber}"]`
  );
  refs.forEach(ref => ref.classList.add("active"));
  _activeRef = refs[0] || null;

  const card = document.getElementById(`citation-${citationNumber}`);
  if (card) {
    card.classList.add("highlighted");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    _activeCard = card;
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (_activeRef)  _activeRef.classList.remove("active");
    if (_activeCard) _activeCard.classList.remove("highlighted");
    _activeRef = null;
    _activeCard = null;
  }
});
