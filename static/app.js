document.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => link.setAttribute('aria-current', 'page')));
