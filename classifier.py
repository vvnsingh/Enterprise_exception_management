import pandas as pd
import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import (
    train_test_split,
    cross_val_score
)
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)

# =====================================================
# LOAD DATASET
# =====================================================

df = pd.read_csv(
    "exception_dataset_100000.csv"
)

print("\n==============================")
print("DATASET STATISTICS")
print("==============================")

print(
    "Total Records:",
    len(df)
)

print(
    "Unique Descriptions:",
    df["Description"].nunique()
)

print(
    "Categories:",
    df["Category"].nunique()
)

# =====================================================
# FEATURES AND LABELS
# =====================================================

X = df["Description"]
y = df["Category"]

# =====================================================
# TRAIN / VALIDATION / TEST SPLIT
# =====================================================

X_train, X_temp, y_train, y_temp = train_test_split(
    X,
    y,
    test_size=0.30,
    random_state=42,
    stratify=y
)

X_val, X_test, y_val, y_test = train_test_split(
    X_temp,
    y_temp,
    test_size=0.50,
    random_state=42,
    stratify=y_temp
)

print("\n==============================")
print("DATA SPLIT")
print("==============================")

print(
    "Training Records:",
    len(X_train)
)

print(
    "Validation Records:",
    len(X_val)
)

print(
    "Testing Records:",
    len(X_test)
)

# =====================================================
# MODEL PIPELINE
# =====================================================

model = Pipeline([
(
'tfidf',
TfidfVectorizer()
),

(
'clf',
MultinomialNB()
)
])

# =====================================================
# TRAIN MODEL
# =====================================================

print("\nTraining Model...")

model.fit(
    X_train,
    y_train
)

# =====================================================
# TRAINING PREDICTIONS
# =====================================================

train_predictions = model.predict(
    X_train
)

training_accuracy = accuracy_score(
    y_train,
    train_predictions
)

# =====================================================
# VALIDATION PREDICTIONS
# =====================================================

val_predictions = model.predict(
    X_val
)

validation_accuracy = accuracy_score(
    y_val,
    val_predictions
)

# =====================================================
# TEST PREDICTIONS
# =====================================================

test_predictions = model.predict(
    X_test
)

test_accuracy = accuracy_score(
    y_test,
    test_predictions
)

# =====================================================
# ACCURACY
# =====================================================

print("\n==============================")
print("MODEL PERFORMANCE")
print("==============================")

print(
    f"Training Accuracy:   {training_accuracy:.4f}"
)

print(
    f"Validation Accuracy: {validation_accuracy:.4f}"
)

print(
    f"Testing Accuracy:    {test_accuracy:.4f}"
)

# =====================================================
# CLASSIFICATION REPORT
# =====================================================

print("\n==============================")
print("CLASSIFICATION REPORT")
print("==============================")

print(classification_report(
    y_test,
    test_predictions
))

print("Test Records:", len(y_test))
print(y_test.head())

# =====================================================
# CONFUSION MATRIX
# =====================================================

print("\n==============================")
print("CONFUSION MATRIX")
print("==============================")

cm = confusion_matrix(
    y_test,
    test_predictions
)

print(cm)

# =====================================================
# CROSS VALIDATION
# =====================================================

print("\n==============================")
print("5-FOLD CROSS VALIDATION")
print("==============================")

cv_scores = cross_val_score(
    model,
    X,
    y,
    cv=5,
    scoring="accuracy"
)

print(
    "Fold Accuracies:",
    cv_scores
)

print(
    "Average CV Accuracy:",
    round(
        cv_scores.mean(),
        4
    )
)

# =====================================================
# SAVE MODEL
# =====================================================

joblib.dump(
    model,
    "models/model.pkl"
)

print("\nModel Saved Successfully")

print(
    "Location: models/model.pkl"
)