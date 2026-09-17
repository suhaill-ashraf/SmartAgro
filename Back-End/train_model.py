"""
SmartAgro Backend — ML Model Training & Prediction
Random Forest Classifier | SKUAST-K 2026
Trains on data/training_data.csv → saves data/spray_model.pkl
predict() function is called by app.py on every /api/decision request.
"""

import os
import pickle
import pandas as pd
import numpy as np
from datetime import datetime

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
)
from sklearn.preprocessing import LabelEncoder

from config import (
    MODEL_PATH,
    TRAINING_DATA_PATH,
    DATA_DIR,
    RANDOM_STATE,
    N_ESTIMATORS,
    TEST_SIZE,
    FEATURES,
    GROWTH_STAGES,
    DECISION_SPRAY,
    DECISION_DELAY,
    DECISION_SKIP,
)


# ════════════════════════════════════════════════
# LOAD TRAINING DATA
# ════════════════════════════════════════════════
def load_training_data() -> pd.DataFrame:
    """
    Loads training_data.csv.
    Raises clear error if file not found — run generate_data.py first.
    """
    if not os.path.exists(TRAINING_DATA_PATH):
        raise FileNotFoundError(
            f"Training data not found at {TRAINING_DATA_PATH}.\n"
            "Run: python generate_data.py"
        )

    df = pd.read_csv(TRAINING_DATA_PATH)

    # Validate required columns exist
    required_cols = FEATURES + ["label"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns in training data: {missing}\n"
            "Regenerate: python generate_data.py"
        )

    print(f"  [ML] Loaded {len(df)} rows from {TRAINING_DATA_PATH}")
    return df


# ════════════════════════════════════════════════
# TRAIN MODEL
# ════════════════════════════════════════════════
def train() -> None:
    """
    Trains Random Forest on training_data.csv.
    Saves model + label encoder to data/spray_model.pkl.
    Prints accuracy, classification report, confusion matrix.
    """
    print("\n" + "=" * 55)
    print("  SMARTAGRO — TRAINING ML MODEL")
    print("=" * 55)
    print(f"  Started    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Estimators : {N_ESTIMATORS}")
    print(f"  Test size  : {TEST_SIZE * 100:.0f}%")
    print(f"  Features   : {FEATURES}")
    print()

    # ── Load data ──
    df = load_training_data()

    # ── Encode label ──
    label_enc = LabelEncoder()
    df["label_encoded"] = label_enc.fit_transform(df["label"])
    print(f"  [ML] Label classes : {list(label_enc.classes_)}")

    # ── Features & target ──
    X = df[FEATURES].values
    y = df["label_encoded"].values

    # ── Train / test split ──
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size    = TEST_SIZE,
        random_state = RANDOM_STATE,
        stratify     = y,    # keeps class balance in both splits
    )
    print(f"  [ML] Train rows : {len(X_train)}")
    print(f"  [ML] Test rows  : {len(X_test)}")
    print()

    # ── Train Random Forest ──
    print("  [ML] Training Random Forest...")
    model = RandomForestClassifier(
        n_estimators = N_ESTIMATORS,
        max_depth    = 10,          # prevents overfitting
        min_samples_split = 5,
        min_samples_leaf  = 2,
        class_weight = "balanced",  # handles any remaining imbalance
        random_state = RANDOM_STATE,
        n_jobs       = -1,          # use all CPU cores
    )
    model.fit(X_train, y_train)
    print("  [ML] Training complete.")
    print()

    # ── Evaluate ──
    y_pred    = model.predict(X_test)
    accuracy  = accuracy_score(y_test, y_pred)

    print(f"  [ML] Test Accuracy : {accuracy * 100:.2f}%")
    print()

    # Cross-validation score (5-fold)
    cv_scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
    print(
        f"  [ML] Cross-Val (5-fold) : "
        f"{cv_scores.mean() * 100:.2f}% ± {cv_scores.std() * 100:.2f}%"
    )
    print()

    # Classification report
    print("  [ML] Classification Report:")
    print(classification_report(
        y_test, y_pred,
        target_names = label_enc.classes_
    ))

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    classes = label_enc.classes_
    print("  [ML] Confusion Matrix:")
    header = "         " + "  ".join(f"{c:>8}" for c in classes)
    print(header)
    for i, row in enumerate(cm):
        row_str = "  ".join(f"{v:>8}" for v in row)
        print(f"  {classes[i]:<8} {row_str}")
    print()

    # Feature importance
    print("  [ML] Feature Importance:")
    importances = model.feature_importances_
    for feat, imp in sorted(
        zip(FEATURES, importances),
        key=lambda x: x[1],
        reverse=True
    ):
        bar = "█" * int(imp * 50)
        print(f"    {feat:<22} {imp:.4f}  {bar}")
    print()

    # ── Save model + encoder ──
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({
            "model":      model,
            "label_enc":  label_enc,
            "features":   FEATURES,
            "accuracy":   round(accuracy * 100, 2),
            "cv_mean":    round(cv_scores.mean() * 100, 2),
            "cv_std":     round(cv_scores.std()  * 100, 2),
            "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "n_rows":     len(df),
            "classes":    list(label_enc.classes_),
        }, f)

    print(f"  [ML] Model saved → {MODEL_PATH}")
    print(f"  [ML] Accuracy    : {accuracy * 100:.2f}%")
    print(f"  Finished : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55 + "\n")


# ════════════════════════════════════════════════
# LOAD MODEL — Called once at Flask startup
# ════════════════════════════════════════════════
_model_cache = None   # In-memory cache — loaded once, reused on every request

def load_model() -> dict:
    """
    Loads model from disk into memory cache.
    Called once at Flask startup — never reloads on every request.
    Raises clear error if model file not found.
    """
    global _model_cache

    if _model_cache is not None:
        return _model_cache

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}.\n"
            "Run: python generate_data.py && python train_model.py"
        )

    with open(MODEL_PATH, "rb") as f:
        _model_cache = pickle.load(f)

    print(
        f"  [ML] Model loaded → accuracy: {_model_cache['accuracy']}% | "
        f"trained: {_model_cache['trained_at']}"
    )
    return _model_cache


# ════════════════════════════════════════════════
# PREDICT — Called by /api/decision on every request
# ════════════════════════════════════════════════
def predict(
    temp_c:           float,
    humidity:         float,
    wind_kmh:         float,
    rain_prob:        float,
    days_since_spray: int,
    growth_stage:     str,
    min_interval:     int,
) -> dict:
    """
    Makes a single spray prediction using the trained model.
    Returns decision + confidence + probabilities for all 3 classes.
    Called by app.py ONLY when all 4 rules have passed.
    """
    try:
        bundle    = load_model()
        model     = bundle["model"]
        label_enc = bundle["label_enc"]

        # Encode growth stage — same method used during training
        if growth_stage in GROWTH_STAGES:
            stage_encoded = GROWTH_STAGES.index(growth_stage)
        else:
            stage_encoded = GROWTH_STAGES.index("Fruit Set")  # fallback

        # Build feature vector — order must match FEATURES list exactly
        feature_vector = np.array([[
            temp_c,
            humidity,
            wind_kmh,
            rain_prob,
            days_since_spray,
            stage_encoded,
            min_interval,
        ]])

        # Predict
        pred_encoded  = model.predict(feature_vector)[0]
        pred_label    = label_enc.inverse_transform([pred_encoded])[0]
        proba         = model.predict_proba(feature_vector)[0]
        confidence    = round(float(max(proba)) * 100, 1)

        # Build probability dict for all 3 classes
        class_probs = {
            label_enc.inverse_transform([i])[0]: round(float(p) * 100, 1)
            for i, p in enumerate(proba)
        }

        return {
            "decision":    pred_label,
            "confidence":  confidence,
            "probabilities": class_probs,
            "model_accuracy": bundle["accuracy"],
        }

    except FileNotFoundError as e:
        return {
            "decision":   DECISION_SPRAY,
            "confidence": 0,
            "probabilities": {},
            "error": str(e),
        }
    except Exception as e:
        return {
            "decision":   DECISION_SPRAY,
            "confidence": 0,
            "probabilities": {},
            "error": f"Prediction error: {str(e)}",
        }


# ════════════════════════════════════════════════
# MAIN — Run directly: python train_model.py
# ════════════════════════════════════════════════
if __name__ == "__main__":
    train()