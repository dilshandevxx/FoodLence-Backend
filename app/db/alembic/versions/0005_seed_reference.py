"""Reference seed data: 9 major allergens + sulfites, additive categories, roles

Revision ID: 0005_seed_reference
Revises: 0004_scans_and_matching
Create Date: 2026-10-11 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0005_seed_reference'
down_revision: Union[str, Sequence[str], None] = '0004_scans_and_matching'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Allergen Groups (9 major FDA + sulfite group)
    op.execute("""
    INSERT INTO kb.allergen_groups (code, name, description, is_major, icon_code, display_order) VALUES
        ('PEANUT',    'Peanut',     'Peanut (groundnut) and products made from it, such as peanut butter and peanut oil.',       true,  'peanut',    1),
        ('TREE_NUT',  'Tree nuts',  'Tree nuts such as almond, cashew, hazelnut, walnut, pistachio and pecan.',                  true,  'tree-nut',  2),
        ('MILK',      'Milk',       'Milk and milk-derived ingredients such as whey, casein, lactose and butter.',                true,  'milk',      3),
        ('EGG',       'Egg',        'Egg and egg-derived ingredients such as albumin, lysozyme and egg powder.',                 true,  'egg',       4),
        ('SOY',       'Soy',        'Soya (soy) and products made from it, such as soy protein, soy sauce and soy lecithin.',    true,  'soy',       5),
        ('WHEAT',     'Wheat',      'Wheat and wheat-derived ingredients such as flour, semolina and wheat starch.',             true,  'wheat',     6),
        ('FISH',      'Fish',       'Fish and fish-derived ingredients such as fish sauce, fish oil and anchovy.',               true,  'fish',      7),
        ('SHELLFISH', 'Shellfish',  'Crustacean shellfish such as prawn, shrimp, crab and lobster, and products made from them.', true, 'shellfish', 8),
        ('SESAME',    'Sesame',     'Sesame seed and products made from it, such as tahini and sesame (gingelly) oil.',          true,  'sesame',    9),
        ('SULFITE',   'Sulfites',   'Sulfur dioxide and sulfite salts (sulphites, E220 to E228) used as preservatives.',         false, 'sulfite',  10)
    ON CONFLICT (code) DO NOTHING;
    """)

    # 2. Additive Categories
    op.execute("""
    INSERT INTO kb.additive_categories (code, name, description) VALUES
        ('PRESERVATIVE',      'Preservative',      'Extends shelf life by inhibiting microbial growth.'),
        ('COLOUR',            'Colour',            'Adds or restores colour to a food product.'),
        ('SWEETENER',         'Sweetener',         'Provides sweetness with little or no sugar.'),
        ('EMULSIFIER',        'Emulsifier',        'Keeps oil and water from separating.'),
        ('STABILISER',        'Stabiliser',        'Maintains the physical structure of a food.'),
        ('FLAVOUR_ENHANCER',  'Flavour enhancer',  'Intensifies existing flavour without adding its own.'),
        ('ANTIOXIDANT',       'Antioxidant',       'Delays oxidation and rancidity.'),
        ('ACIDITY_REGULATOR', 'Acidity regulator', 'Controls the acidity or alkalinity of a food.'),
        ('THICKENER',         'Thickener',         'Increases viscosity without changing other properties.'),
        ('RAISING_AGENT',     'Raising agent',     'Releases gas to increase the volume of dough or batter.')
    ON CONFLICT (code) DO NOTHING;
    """)

    # 3. Roles
    op.execute("""
    INSERT INTO app.roles (code, name) VALUES
        ('USER',  'Registered User'),
        ('ADMIN', 'Administrator')
    ON CONFLICT (code) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM app.roles WHERE code IN ('USER', 'ADMIN');")
    op.execute("""
    DELETE FROM kb.additive_categories
     WHERE code IN (
         'PRESERVATIVE', 'COLOUR', 'SWEETENER', 'EMULSIFIER', 'STABILISER',
         'FLAVOUR_ENHANCER', 'ANTIOXIDANT', 'ACIDITY_REGULATOR', 'THICKENER', 'RAISING_AGENT'
     );
    """)
    op.execute("""
    DELETE FROM kb.allergen_groups
     WHERE code IN ('PEANUT', 'TREE_NUT', 'MILK', 'EGG', 'SOY', 'WHEAT', 'FISH', 'SHELLFISH', 'SESAME', 'SULFITE');
    """)
