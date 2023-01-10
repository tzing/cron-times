'use strict';

const crontimes = (function () {
    const FORMAT_BRIEF_DATE = 'MMM DD';
    const FORMAT_BRIEF_TIME = 'HH:mm';
    const FORMAT_DETAIL_TIME = 'YYYY-MM-DD HH:mm:ss Z';
    const STORAGE_KEY_TIME_ZONE = 'timeZone';

    const cardNow = document.getElementById('card-now');
    const timetable = document.getElementById('timetable');

    let currentTimeZone = null;

    /**
     * Get timezone settings, use browser locale by defult.
     */
    function getTimezone() {
        return currentTimeZone
            || localStorage.getItem(STORAGE_KEY_TIME_ZONE)
            || Intl.DateTimeFormat().resolvedOptions().timeZone;
    }

    /**
     * Set timezone
     * @param {string} v
     */
    function setTimeZone(v) {
        currentTimeZone = v;
        localStorage.setItem(STORAGE_KEY_TIME_ZONE, v);
        refreshTimes();
    }

    /**
     * Scroll the page for centering the 'now' card
     */
    function scrollToNow() {
        cardNow.scrollIntoView({ block: 'center' });
    }

    /**
     * Refresh all time cards with selected timezone
     */
    function refreshTimes() {
        // cut card
        cardNow.remove();

        // refresh time labels
        document.querySelectorAll('.time').forEach((e) => {
            updateTime(e.closest('.card'));
        });

        // move 'now' card
        insertCurrentTime();
    }

    /**
     * Insert a card for current time in selected timezone
     */
    function insertCurrentTime() {
        // find the closest card to be started
        let now = dayjs().tz(getTimezone());
        let nextDom = undefined;
        for (let dom of timetable.querySelectorAll('.time')) {
            let t = dayjs(dom.dataset.datetime);
            if (t.isAfter(now)) {
                nextDom = dom;
                break;
            }
        }

        // insert card
        if (nextDom) {
            let card = nextDom.closest('.card').closest('.row');
            timetable.insertBefore(cardNow, card);
        } else {
            timetable.appendChild(cardNow);
        }

        // update time
        let dom = cardNow.querySelector('.time');
        dom.innerHTML = `<h4>${now.format(FORMAT_BRIEF_TIME)}</h4>`;
    }

    /**
     * Update the time in a card to selected timezone
     * @param {HTMLElement} card
     */
    function updateTime(card) {
        let domBriefTime = card.querySelector('.time'),
            dateTime = dayjs(domBriefTime.dataset.datetime).tz(getTimezone());

        // brief time
        let briefTime = '';
        if (!dateTime.isToday()) {
            if (dateTime.isTomorrow()) {
                briefTime = 'Tomorrow';
            } else if (dateTime.isYesterday()) {
                briefTime = 'Yesterday';
            } else {
                briefTime = dateTime.format(FORMAT_BRIEF_DATE);
            }
        }

        briefTime += `<h4>${dateTime.format(FORMAT_BRIEF_TIME)}</h4>`;

        domBriefTime.innerHTML = briefTime

        // detail time
        card.querySelector('.detail-time').innerHTML = dateTime.format(FORMAT_DETAIL_TIME);

        // relative time
        card.querySelector('.relative-time').innerHTML = dateTime.from();
    }

    /**
     * Only show jobs that matches selected properties.
     * @param {string} target
     */
    function filterJobs(target) {
        for (let cardDom of timetable.querySelectorAll('.card')) {
            let row = cardDom.closest('.row');
            if (row.id === 'card-now') {
                continue;
            }

            if (!target) {
                row.classList.remove('hide');
            } else if (row.classList.contains(target)) {
                row.classList.remove('hide');
            } else {
                row.classList.add('hide');
            }
        }
    }

    return {
        filterJobs: filterJobs,
        getTimezone: getTimezone,
        refreshTimes: refreshTimes,
        scrollToNow: scrollToNow,
        setTimeZone: setTimeZone,
    }
})();
