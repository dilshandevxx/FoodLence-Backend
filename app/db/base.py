from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy declarative models in FoodLence.
    """
    pass


# Import all models to ensure they are registered on Base.metadata for Alembic migrations
from app.models.user import User  # noqa: E402, F401
from app.models.profile import Profile  # noqa: E402, F401
from app.models.allergen import Allergen  # noqa: E402, F401
from app.models.ingredient import Ingredient  # noqa: E402, F401
from app.models.ingredient_allergen_map import IngredientAllergenMap  # noqa: E402, F401
from app.models.additive import Additive  # noqa: E402, F401
from app.models.ingredient_embedding import IngredientEmbedding  # noqa: E402, F401
from app.models.inference_log import InferenceLog  # noqa: E402, F401
