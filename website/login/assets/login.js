(() => {
  const params = new URLSearchParams(window.location.search);
  const nextParam = params.get("next");
  const nextField = document.querySelector("[data-next-field]");
  if (nextParam && nextField) {
    nextField.value = nextParam;
  }

  const hasError = params.has("error");
  const errorBox = document.querySelector("[data-error]");
  if (errorBox) {
    errorBox.hidden = !hasError;
  }
})();
