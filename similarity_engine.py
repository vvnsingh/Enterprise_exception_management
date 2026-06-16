from sklearn.feature_extraction.text import TfidfVectorizer

from sklearn.metrics.pairwise import cosine_similarity

def check_similarity(
    new_text,
    historical_texts
):

    corpus = [new_text]

    corpus.extend(
        historical_texts
    )

    vectorizer = TfidfVectorizer()

    vectors = vectorizer.fit_transform(
        corpus
    )

    similarities = cosine_similarity(
        vectors[0:1],
        vectors[1:]
    )

    return similarities[0]