from agent.skills import google_maps_search, news_search, youtube_search, calculate

def test_google_maps_search():
    assert "google.com/maps/search" in google_maps_search("Одесса")

def test_news_search():
    assert "news.google.com/search" in news_search("технологии")

def test_youtube_search():
    assert "youtube.com/results" in youtube_search("Jarvis")

def test_calculate_still_works():
    assert "2 + 2 = 4" == calculate("2 + 2")
