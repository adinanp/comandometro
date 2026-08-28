document.addEventListener("DOMContentLoaded", function () {
  const $ = django.jQuery;

  function updateDeckState(rowPrefix) {
    const playerSelect = $("#" + rowPrefix + "-player");
    const deckSelect = $("#" + rowPrefix + "-deck");
    const addDeckBtn = $("#" + rowPrefix + "-deck")
      .closest("td, .form-row")
      .find(".related-widget-wrapper-link, a.add-related");
    const playerId = playerSelect.val();

    if (!playerId) {
      deckSelect.prop("disabled", true);
      deckSelect
        .empty()
        .append(
          '<option value="">--- Selecione um jogador primeiro ---</option>',
        );
      if (addDeckBtn.length) addDeckBtn.css("display", "none");
      return;
    }

    deckSelect.prop("disabled", false);
    if (addDeckBtn.length) {
      addDeckBtn.css("display", "inline-block");

      addDeckBtn.each(function () {
        let btn = $(this);
        let href = btn.attr("data-href-template") || btn.attr("href") || "";

        if (href) {
          let baseHref = href.split("?")[0];
          let urlParams = new URLSearchParams(href.split("?")[1] || "");
          urlParams.set("player", playerId);

          let newHref = baseHref + "?" + urlParams.toString();
          btn.attr("href", newHref);
          if (btn.attr("data-href-template")) {
            btn.attr("data-href-template", newHref);
          }
        }
      });
    }

    $.ajax({
      url: `/admin/core/game/get-player-decks/${playerId}/`,
      type: "GET",
      success: function (data) {
        const currentVal = deckSelect.val();
        deckSelect.empty().append('<option value="">---------</option>');
        $.each(data.decks, function (index, deck) {
          deckSelect.append(new Option(deck.name, deck.id));
        });
        if (currentVal) {
          deckSelect.val(currentVal);
        }
      },
    });
  }

  $('select[id^="id_participants-"][id$="-player"]').each(function () {
    const rowPrefix = $(this).attr("id").replace("-player", "");
    updateDeckState(rowPrefix);
  });

  $(document).on(
    "change select2:select select2:clear",
    'select[id^="id_participants-"][id$="-player"]',
    function () {
      const rowPrefix = $(this).attr("id").replace("-player", "");
      updateDeckState(rowPrefix);
    },
  );

  $(document).on(
    "click",
    'a[id*="-deck"], .field-deck a.add-related',
    function (e) {
      const rowPrefix = $(this)
        .closest("tr, .form-row")
        .find('select[id$="-player"]')
        .attr("id")
        ?.replace("-player", "");
      if (rowPrefix) {
        updateDeckState(rowPrefix);
      }
    },
  );
});
