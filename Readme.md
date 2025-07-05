## Parliamentary proceedings data

The data published at https://sansad.in/ls/questions/questions-and-answers?1 covers every question asked in the Indian Parliament, along with debates and allied proceedings. It's a national treasure—funded by taxpayers—and it **should be freely and easily accessible to everyone.**

I've already scraped the full archive and turned it into a continuously updated database. A self-hosted API is live so anyone can download the raw records without jumping through hoops.

Raw dumps, however, have limited value on their own. The next step is to process the documents to make them truly useful. My plan is to build a RAG-style chat interface where you can ask, say, _"What did the Finance Minister say about inflation in the last three sessions?"_ and get a cited answer in seconds.

Paid LLM APIs would solve this neatly, but they're far too expensive for an open project. Self-hosting smaller, quantised models cuts the cost, yet the hardware bills are starting to add up—and they'll only grow as the corpus grows.

This project will **always** remain open source, and the data will **always** stay free. If you'd like to help—whether by contributing code, documentation, infrastructure, or a few rupees/dollars towards server costs—please reach out. Let's keep our Parliament's data truly public.