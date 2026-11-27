-- =============================================================================
--  FoodLence Knowledge Base Seed — Additives (100+ E-Numbers)
--  Target Tables: kb.ingredients (subtype: additive), kb.additive_details
--  Owner: S.K.P.H. Deemantha (22CSE0348) — Knowledge Base Lead
--  Standard: EFSA Food Additive Database / CODEX Alimentarius Class Names
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS kb;

WITH raw_additives (slug, canonical_name, e_number, cat_code, concern, explanation) AS (
    VALUES
    -- ---- Colours (E100 - E182) ---------------------------------------------
    ('e100_curcumin', 'Curcumin', 'E100', 'COLOUR', 1, 'Natural yellow-orange pigment extracted from turmeric rhizomes. Generally considered safe.'),
    ('e101_riboflavin', 'Riboflavin', 'E101', 'COLOUR', 1, 'Vitamin B2; provides an intense yellow colour. Essential micronutrient.'),
    ('e102_tartrazine', 'Tartrazine', 'E102', 'COLOUR', 2, 'Synthetic lemon-yellow azo dye. May trigger intolerance symptoms or hyperactivity in sensitive children.'),
    ('e104_quinoline_yellow', 'Quinoline Yellow', 'E104', 'COLOUR', 2, 'Synthetic greenish-yellow dye. Restricted or cautioned in certain jurisdictions for children.'),
    ('e110_sunset_yellow', 'Sunset Yellow FCF', 'E110', 'COLOUR', 2, 'Synthetic orange-yellow azo dye used in confectionery and beverages. Can cause hypersensitivity in aspirin-intolerant individuals.'),
    ('e120_carmine', 'Carmine', 'E120', 'COLOUR', 3, 'Crimson red pigment extracted from dried cochineal insects (Dactylopius coccus). Known to trigger severe allergic IgE-mediated reactions and asthma.'),
    ('e122_carmoisine', 'Carmoisine', 'E122', 'COLOUR', 2, 'Synthetic red azo dye (Azorubine). Evaluated by EFSA; may trigger hives or asthma in sensitive individuals.'),
    ('e123_amaranth', 'Amaranth', 'E123', 'COLOUR', 2, 'Dark red to purple azo dye. Strictly limited in the EU and banned in several countries.'),
    ('e124_ponceau_4r', 'Ponceau 4R', 'E124', 'COLOUR', 2, 'Synthetic strawberry red azo dye. Frequently found in soft drinks and dessert mixes; subject to activity warnings in children.'),
    ('e127_erythrosine', 'Erythrosine', 'E127', 'COLOUR', 2, 'Cherry-pink synthetic fluorine dye. Primarily permitted in maraschino cherries and cocktail mixers.'),
    ('e129_allura_red', 'Allura Red AC', 'E129', 'COLOUR', 2, 'Red azo dye widely used in snack foods and sweets. Safe for the general population, caution advised for sensitive individuals.'),
    ('e131_patent_blue_v', 'Patent Blue V', 'E131', 'COLOUR', 2, 'Synthetic dark blue dye. Low toxicity, but allergic reactions such as urticaria are occasionally documented.'),
    ('e132_indigotine', 'Indigotine', 'E132', 'COLOUR', 1, 'Synthetic indigo carmine dye providing blue hue in confections and beverages.'),
    ('e133_brilliant_blue', 'Brilliant Blue FCF', 'E133', 'COLOUR', 1, 'Synthetic bright blue dye. Poorly absorbed through the gastrointestinal tract and largely eliminated unchanged.'),
    ('e140_chlorophyll', 'Chlorophyll', 'E140', 'COLOUR', 1, 'Natural green plant pigment extracted from spinach and alfalfa. Deemed safe with no known adverse effects.'),
    ('e141_copper_chlorophyll', 'Copper Chlorophyll', 'E141', 'COLOUR', 1, 'Semisynthetic stable green food colouring derived from chlorophyll complexes.'),
    ('e150a_plain_caramel', 'Plain Caramel', 'E150a', 'COLOUR', 1, 'Natural brown colorant made by controlled heating of carbohydrates. Widely used in whiskey, baked goods, and syrups.'),
    ('e150b_caustic_sulfite_caramel', 'Caustic Sulfite Caramel', 'E150b', 'COLOUR', 2, 'Caramel color prepared with sulfite compounds. Contains trace sulfites that may require declaration.'),
    ('e150c_ammonia_caramel', 'Ammonia Caramel', 'E150c', 'COLOUR', 1, 'Brown colorant prepared with ammonium compounds. Used in beer, sauces, and confectionery.'),
    ('e150d_sulfite_ammonia_caramel', 'Sulfite Ammonia Caramel', 'E150d', 'COLOUR', 2, 'Caramel colorant manufactured using both ammonium and sulfite reactants. Common in dark colas.'),
    ('e151_brilliant_black', 'Brilliant Black BN', 'E151', 'COLOUR', 2, 'Synthetic black diazo dye used in brown sauces and caviar substitutes.'),
    ('e153_vegetable_carbon', 'Vegetable Carbon', 'E153', 'COLOUR', 1, 'Insoluble black pigment produced by carbonising vegetable matter. Natural and inert.'),
    ('e160a_beta_carotene', 'Beta-carotene', 'E160a', 'COLOUR', 1, 'Pro-vitamin A provitamins giving an orange-yellow shade. Safe and nutritionally beneficial in food.'),
    ('e160b_annatto', 'Annatto', 'E160b', 'COLOUR', 2, 'Natural reddish-orange condiment and colorant derived from achiote tree seeds (Bixin/Norbixin). Known rare trigger of food-protein allergies.'),
    ('e160c_paprika_extract', 'Paprika Extract', 'E160c', 'COLOUR', 1, 'Natural deep red oil derived from sweet red peppers (Capsanthin/Capsorubin). Safe for consumption.'),
    ('e160d_lycopene', 'Lycopene', 'E160d', 'COLOUR', 1, 'Bright red carotene carotenoid found naturally in tomatoes and red carrots.'),
    ('e160e_beta_apo_8_carotenal', 'Beta-apo-8-carotenal', 'E160e', 'COLOUR', 1, 'Carotenoid pigment providing orange-red color, naturally present in citrus fruits and spinach.'),
    ('e161b_lutein', 'Lutein', 'E161b', 'COLOUR', 1, 'Natural yellow xanthophyll carotenoid extracted from marigold petals (Tagetes erecta). Promotes retinal health.'),
    ('e162_beetroot_red', 'Beetroot Red', 'E162', 'COLOUR', 1, 'Natural red pigment (betanin) extracted from red beetroots. Safe natural food colouring.'),
    ('e163_anthocyanins', 'Anthocyanins', 'E163', 'COLOUR', 1, 'Natural red, purple, and blue pigments extracted from grape skins, blackcurrants, and berries.'),
    ('e170_calcium_carbonate', 'Calcium Carbonate', 'E170', 'COLOUR', 1, 'Inorganic mineral surface colorant and anti-caking agent derived from chalk and limestone.'),
    ('e171_titanium_dioxide', 'Titanium Dioxide', 'E171', 'COLOUR', 3, 'Inorganic white pigment. Banned in food products within the European Union (2022) due to genotoxicity concerns.'),
    ('e172_iron_oxides', 'Iron Oxides', 'E172', 'COLOUR', 1, 'Yellow, red, and black mineral colorants used in glazes, coatings, and confectionery decorations.'),

    -- ---- Preservatives (E200 - E297) ---------------------------------------
    ('e200_sorbic_acid', 'Sorbic Acid', 'E200', 'PRESERVATIVE', 1, 'Organic antimicrobial agent that prevents mold and yeast proliferation in dairy, cheese, and baked goods.'),
    ('e202_potassium_sorbate', 'Potassium Sorbate', 'E202', 'PRESERVATIVE', 1, 'Widely used water-soluble antimicrobial salt preventing fungi and yeast growth in juices, jams, and dairy.'),
    ('e203_calcium_sorbate', 'Calcium Sorbate', 'E203', 'PRESERVATIVE', 1, 'Sorbate salt preserving cheese and dried fruit; safe and metabolized like natural fatty acids.'),
    ('e210_benzoic_acid', 'Benzoic Acid', 'E210', 'PRESERVATIVE', 2, 'Antimicrobial preservative effective in acidic conditions. Can trigger asthma attacks or hives in sensitive individuals.'),
    ('e211_sodium_benzoate', 'Sodium Benzoate', 'E211', 'PRESERVATIVE', 2, 'Sodium salt of benzoic acid; ubiquitous in carbonated beverages and salad dressings. Evaluated for potential benzene formation in ascorbic acid combinations.'),
    ('e212_potassium_benzoate', 'Potassium Benzoate', 'E212', 'PRESERVATIVE', 2, 'Potassium preservative salt used as an alternative to sodium benzoate in low-sodium beverages.'),
    ('e213_calcium_benzoate', 'Calcium Benzoate', 'E213', 'PRESERVATIVE', 2, 'Benzoate preservative used in pickled vegetables and concentrates.'),
    ('e220_sulfur_dioxide', 'Sulfur Dioxide', 'E220', 'PRESERVATIVE', 3, 'Gaseous preservative used in dried fruits, wine, and juices. Regulated allergen: potent trigger for asthmatics and sulfite-sensitive persons.'),
    ('e221_sodium_sulfite', 'Sodium Sulfite', 'E221', 'PRESERVATIVE', 3, 'Inorganic sulfite salt that prevents browning and bacterial spoilage. Must be declared as a sulfite allergen above 10 mg/kg.'),
    ('e222_sodium_hydrogen_sulfite', 'Sodium Hydrogen Sulfite', 'E222', 'PRESERVATIVE', 3, 'Sulfite preservative and bleach in fruit processing. Triggers sulfite hypersensitivity reactions.'),
    ('e223_sodium_metabisulfite', 'Sodium Metabisulfite', 'E223', 'PRESERVATIVE', 3, 'Common antioxidant and preservative in biscuits, dehydrated potatoes, and wine. High allergenic concern for asthmatics.'),
    ('e224_potassium_metabisulfite', 'Potassium Metabisulfite', 'E224', 'PRESERVATIVE', 3, 'Primary winemaking antioxidant and preservative. Regulated allergen triggering acute bronchoconstriction in sensitive individuals.'),
    ('e226_calcium_sulfite', 'Calcium Sulfite', 'E226', 'PRESERVATIVE', 3, 'Sulfite salt used in cider and sugar syrup processing. Allergenic sulfite source.'),
    ('e227_calcium_hydrogen_sulfite', 'Calcium Hydrogen Sulfite', 'E227', 'PRESERVATIVE', 3, 'Sulfite compound used in beer brewing and preserved cherries.'),
    ('e228_potassium_hydrogen_sulfite', 'Potassium Hydrogen Sulfite', 'E228', 'PRESERVATIVE', 3, 'Sulfite chemical agent used in fruit and vegetable pulp preservation.'),
    ('e234_nisin', 'Nisin', 'E234', 'PRESERVATIVE', 1, 'Natural antibacterial polycyclic peptide produced by Lactococcus lactis. Commonly used in processed cheese and pudding.'),
    ('e235_natamycin', 'Natamycin', 'E235', 'PRESERVATIVE', 1, 'Antifungal polyene macrolide applied to the rind of hard cheeses and dried sausages to halt mold growth.'),
    ('e249_potassium_nitrite', 'Potassium Nitrite', 'E249', 'PRESERVATIVE', 2, 'Curing agent and preservative in meats that inhibits Clostridium botulinum growth.'),
    ('e250_sodium_nitrite', 'Sodium Nitrite', 'E250', 'PRESERVATIVE', 2, 'Critical meat curing salt responsible for pink color and botulism protection. Intake should be moderated due to nitrosamine potential.'),
    ('e251_sodium_nitrate', 'Sodium Nitrate', 'E251', 'PRESERVATIVE', 2, 'Nitrate salt used in curing bacon, ham, and certain cheeses.'),
    ('e252_potassium_nitrate', 'Potassium Nitrate', 'E252', 'PRESERVATIVE', 2, 'Saltpeter; traditional cured meat preservative preventing pathogenic bacterial growth.'),
    ('e260_acetic_acid', 'Acetic Acid', 'E260', 'PRESERVATIVE', 1, 'Primary acid found in vinegar. Used as a safe preservative, flavorant, and acidity regulator.'),
    ('e261_potassium_acetate', 'Potassium Acetate', 'E261', 'PRESERVATIVE', 1, 'Salt of acetic acid used to adjust pH and control microbial spoilage.'),
    ('e262_sodium_acetate', 'Sodium Acetate', 'E262', 'PRESERVATIVE', 1, 'Salt of acetic acid; provides salt-and-vinegar seasoning flavor and buffering capacity.'),
    ('e270_lactic_acid', 'Lactic Acid', 'E270', 'PRESERVATIVE', 1, 'Naturally occurring organic acid produced by fermentation. Deemed entirely safe for general diets.'),
    ('e280_propionic_acid', 'Propionic Acid', 'E280', 'PRESERVATIVE', 1, 'Natural short-chain fatty acid that inhibits mold growth in commercial bread and bakery goods.'),
    ('e281_sodium_propionate', 'Sodium Propionate', 'E281', 'PRESERVATIVE', 1, 'Propionate salt preventing rope and mold in sliced breads and pastries.'),
    ('e282_calcium_propionate', 'Calcium Propionate', 'E282', 'PRESERVATIVE', 1, 'Standard industrial bread preservative preventing mold formation. Well tolerated by humans.'),
    ('e283_potassium_propionate', 'Potassium Propionate', 'E283', 'PRESERVATIVE', 1, 'Low-sodium bakery preservative inhibiting molds and spores.'),

    -- ---- Antioxidants (E300 - E321) ----------------------------------------
    ('e300_ascorbic_acid', 'Ascorbic Acid', 'E300', 'ANTIOXIDANT', 1, 'Vitamin C; powerful natural antioxidant preventing fruit browning and dough oxidation.'),
    ('e301_sodium_ascorbate', 'Sodium Ascorbate', 'E301', 'ANTIOXIDANT', 1, 'Mineral salt of vitamin C used to protect meat color and prevent oxidation in beverages.'),
    ('e302_calcium_ascorbate', 'Calcium Ascorbate', 'E302', 'ANTIOXIDANT', 1, 'Neutral non-acidic vitamin C salt used to extend freshness in canned vegetables and baby foods.'),
    ('e304_ascorbyl_palmitate', 'Ascorbyl Palmitate', 'E304', 'ANTIOXIDANT', 1, 'Fat-soluble ester of vitamin C that protects vegetable oils and potato crisps from turning rancid.'),
    ('e306_tocopherol_extract', 'Tocopherol-rich Extract', 'E306', 'ANTIOXIDANT', 1, 'Natural mixed vitamin E extract. Protects fats, oils, and cereals against oxidative rancidity.'),
    ('e307_alpha_tocopherol', 'Alpha-tocopherol', 'E307', 'ANTIOXIDANT', 1, 'Synthetic pure vitamin E antioxidant preventing lipid oxidation.'),
    ('e310_propyl_gallate', 'Propyl Gallate', 'E310', 'ANTIOXIDANT', 2, 'Synthetic phenolic antioxidant used to stabilize edible fats, chewing gum, and instant noodles.'),
    ('e319_tbhq', 'TBHQ', 'E319', 'ANTIOXIDANT', 2, 'Tertiary butylhydroquinone; highly effective antioxidant in vegetable frying oils and crackers. Regulated daily intake.'),
    ('e320_bha', 'BHA', 'E320', 'ANTIOXIDANT', 2, 'Butylated hydroxyanisole; synthetic antioxidant preserving fats and potato chips. Kept within strict statutory limits.'),
    ('e321_bht', 'BHT', 'E321', 'ANTIOXIDANT', 2, 'Butylated hydroxytoluene; lipid stabilizer in breakfast cereals and snack packaging.'),
    ('e330_citric_acid', 'Citric Acid', 'E330', 'ACIDITY_REGULATOR', 1, 'Natural organic tricarboxylic acid found in citrus fruits. Universally used for tart flavor and pH control.'),
    ('e331_sodium_citrate', 'Sodium Citrate', 'E331', 'ACIDITY_REGULATOR', 1, 'Sodium salt of citric acid; acts as an emulsifying salt in processed cheese and electrolyte buffer in sports drinks.'),
    ('e332_potassium_citrate', 'Potassium Citrate', 'E332', 'ACIDITY_REGULATOR', 1, 'Buffering agent and acidity regulator in soft drinks and jams.'),
    ('e334_tartaric_acid', 'Tartaric Acid', 'E334', 'ACIDITY_REGULATOR', 1, 'Natural organic acid found in grapes and tamarind; gives sourness to candies and baking leavening.'),
    ('e338_phosphoric_acid', 'Phosphoric Acid', 'E338', 'ACIDITY_REGULATOR', 1, 'Inorganic mineral acid used to provide sharp, tangy acidity specifically in dark cola beverages.'),

    -- ---- Emulsifiers, Stabilisers & Thickeners (E322, E400 - E495) ---------
    ('e322_lecithin', 'Lecithin', 'E322', 'EMULSIFIER', 2, 'Phospholipid mixture extracted primarily from soybeans or eggs. Critical allergen source if derived from soy or egg without complete protein isolation.'),
    ('e400_alginic_acid', 'Alginic Acid', 'E400', 'THICKENER', 1, 'Natural polysaccharide extracted from brown seaweeds. Gelling agent in desserts and ice cream.'),
    ('e401_sodium_alginate', 'Sodium Alginate', 'E401', 'THICKENER', 1, 'Alginate salt forming viscous solutions; key ingredient in edible films, molecular gastronomy, and dairy puddings.'),
    ('e406_agar', 'Agar', 'E406', 'STABILISER', 1, 'Natural plant-based gelatin substitute derived from red algae (Rhodophyta). Vegetarian gelling agent.'),
    ('e407_carrageenan', 'Carrageenan', 'E407', 'STABILISER', 2, 'Sulfated polysaccharide extracted from red seaweed. Used to stabilize dairy chocolate milk, vegan dairy alternatives, and deli meats.'),
    ('e410_locust_bean_gum', 'Locust Bean Gum', 'E410', 'THICKENER', 1, 'Galactomannan vegetable gum extracted from carob tree seeds (Ceratonia siliqua). Prevents syneresis in cream cheese.'),
    ('e412_guar_gum', 'Guar Gum', 'E412', 'THICKENER', 1, 'Natural seed gum from the guar plant (Cyamopsis tetragonoloba). Enhances viscosity in sauces, ice cream, and gluten-free baking.'),
    ('e414_gum_arabic', 'Gum Arabic', 'E414', 'STABILISER', 1, 'Acacia tree gum exudate used to stabilize beverage flavor emulsions and coat hard candies.'),
    ('e415_xanthan_gum', 'Xanthan Gum', 'E415', 'THICKENER', 1, 'Polysaccharide fermented by Xanthomonas campestris. Essential binder in gluten-free foods and salad dressings.'),
    ('e416_karaya_gum', 'Karaya Gum', 'E416', 'THICKENER', 1, 'Natural tree gum used in meringues and toppings.'),
    ('e417_tara_gum', 'Tara Gum', 'E417', 'THICKENER', 1, 'Seed gum from Caesalpinia spinosa used as an ice-cream stabilizer.'),
    ('e418_gellan_gum', 'Gellan Gum', 'E418', 'STABILISER', 1, 'Fermentation gum creating fluid gels in plant-based milks to keep calcium in suspension.'),
    ('e420_sorbitol', 'Sorbitol', 'E420', 'SWEETENER', 1, 'Sugar alcohol (polyol) with 60% sweetness of sucrose. Acts as humectant in confectionery; excessive consumption can cause laxative effect.'),
    ('e421_mannitol', 'Mannitol', 'E421', 'SWEETENER', 1, 'Polyol dusting agent on chewing gums preventing sticking.'),
    ('e422_glycerol', 'Glycerol', 'E422', 'EMULSIFIER', 1, 'Glycerin; sweet-tasting polyol compound used as a solvent and moisture-retaining humectant in soft cakes.'),
    ('e440_pectin', 'Pectin', 'E440', 'THICKENER', 1, 'Natural plant structural carbohydrate from citrus peels and apples. Gelling agent in fruit jams and jellies.'),
    ('e450_diphosphates', 'Diphosphates', 'E450', 'STABILISER', 1, 'Mineral phosphate salts that retain moisture in cured meats and act as slow-acting leavening acids in biscuits.'),
    ('e451_triphosphates', 'Triphosphates', 'E451', 'STABILISER', 1, 'Food-grade phosphates retaining natural juices in frozen seafood and poultry fillets.'),
    ('e452_polyphosphates', 'Polyphosphates', 'E452', 'STABILISER', 1, 'Sequestrants and emulsifiers used in processed cheeses to prevent oil separation.'),
    ('e460_cellulose', 'Cellulose', 'E460', 'STABILISER', 1, 'Purified plant dietary fiber used as an anti-caking agent in shredded cheeses and bulking fiber in low-calorie snacks.'),
    ('e461_methyl_cellulose', 'Methyl Cellulose', 'E461', 'THICKENER', 1, 'Vegetable-derived binder that gels upon heating; common texturizer in plant-based burger patties.'),
    ('e466_carboxymethyl_cellulose', 'Carboxymethyl Cellulose', 'E466', 'THICKENER', 1, 'Cellulose gum used to impart creaminess to light ice creams and stabilize dressings.'),
    ('e471_mono_and_diglycerides', 'Mono- and Diglycerides of Fatty Acids', 'E471', 'EMULSIFIER', 1, 'Plant- or animal-derived fatty acid emulsifiers that soften bread crumb and blend margarine.'),
    ('e472e_datem', 'DATEM', 'E472e', 'EMULSIFIER', 1, 'Diacetyl tartaric acid esters of mono- and diglycerides. Premier dough conditioner ensuring high bread volume and crispy crust.'),
    ('e475_polyglycerol_esters', 'Polyglycerol Esters of Fatty Acids', 'E475', 'EMULSIFIER', 1, 'Emulsifiers optimizing aeration and volume in bakery sponge cakes.'),
    ('e476_pgpr', 'Polyglycerol Polyricinoleate', 'E476', 'EMULSIFIER', 1, 'Castor-bean derived emulsifier reducing chocolate viscosity and enabling smooth thin coatings.'),
    ('e481_sodium_stearoyl_lactylate', 'Sodium Stearoyl Lactylate', 'E481', 'EMULSIFIER', 1, 'Lactylate dough conditioner and shelf-life extender in packaged bread and tortillas.'),
    ('e482_calcium_stearoyl_lactylate', 'Calcium Stearoyl Lactylate', 'E482', 'EMULSIFIER', 1, 'Dough strengthener and whipping agent in pancake batters and bakery doughs.'),
    ('e491_sorbitan_monostearate', 'Sorbitan Monostearate', 'E491', 'EMULSIFIER', 1, 'Span 60; rehydration aid in active dry yeast and gloss enhancer in confectionery coatings.'),

    -- ---- Acidity Regulators & Raising Agents (E500 - E553) -----------------
    ('e500_sodium_carbonates', 'Sodium Carbonates', 'E500', 'RAISING_AGENT', 1, 'Sodium bicarbonate (baking soda) releasing carbon dioxide when combined with acids to leaven cakes.'),
    ('e501_potassium_carbonates', 'Potassium Carbonates', 'E501', 'RAISING_AGENT', 1, 'Potassium salts used for alkalizing cocoa (Dutch processing) and leavening low-sodium bakery products.'),
    ('e503_ammonium_carbonates', 'Ammonium Carbonates', 'E503', 'RAISING_AGENT', 1, 'Baker''s ammonia; classical leavening agent creating exceptionally crisp cookies, crackers, and biscuits.'),
    ('e504_magnesium_carbonates', 'Magnesium Carbonates', 'E504', 'ACIDITY_REGULATOR', 1, 'Anticaking agent in table salts and buffering base in chewing gums.'),
    ('e508_potassium_chloride', 'Potassium Chloride', 'E508', 'FLAVOUR_ENHANCER', 1, 'Salt substitute used to reduce sodium content in soups, snacks, and cured products.'),
    ('e509_calcium_chloride', 'Calcium Chloride', 'E509', 'STABILISER', 1, 'Firming agent for canned tomatoes, pickle brines, and tofu curdling coagulant.'),
    ('e516_calcium_sulfate', 'Calcium Sulfate', 'E516', 'STABILISER', 1, 'Gypsum; traditional firming coagulant in silken and firm tofu manufacturing.'),
    ('e524_sodium_hydroxide', 'Sodium Hydroxide', 'E524', 'ACIDITY_REGULATOR', 1, 'Caustic alkali used strictly in surface pretzel dipping for characteristic brown crust and gloss.'),
    ('e541_sodium_aluminium_phosphate', 'Sodium Aluminium Phosphate', 'E541', 'RAISING_AGENT', 1, 'Slow-reacting leavening acid providing oven rise in prepared cake mixes.'),
    ('e551_silicon_dioxide', 'Silicon Dioxide', 'E551', 'STABILISER', 1, 'Silica anticaking agent keeping seasonings, instant coffee, and spice blends free-flowing.'),
    ('e553b_talc', 'Talc', 'E553b', 'STABILISER', 1, 'Food-grade talc used as a dusting and release agent in chewing gum and rice polishing.'),

    -- ---- Flavour Enhancers (E620 - E635) -----------------------------------
    ('e620_glutamic_acid', 'Glutamic Acid', 'E620', 'FLAVOUR_ENHANCER', 1, 'Non-essential amino acid delivering savory umami taste profile.'),
    ('e621_monosodium_glutamate', 'Monosodium Glutamate', 'E621', 'FLAVOUR_ENHANCER', 1, 'MSG; pure umami taste seasoning. Extensively researched and validated safe by FAO/WHO and FDA.'),
    ('e627_disodium_guanylate', 'Disodium Guanylate', 'E627', 'FLAVOUR_ENHANCER', 1, 'Nucleotide flavour enhancer naturally found in mushrooms; works synergistically with MSG to intensify savoriness.'),
    ('e631_disodium_inosinate', 'Disodium Inosinate', 'E631', 'FLAVOUR_ENHANCER', 1, 'Nucleotide flavour enhancer prepared from meat or fermented tapioca; amplifies savory taste tenfold.'),
    ('e635_disodium_5_ribonucleotides', 'Disodium 5-ribonucleotides', 'E635', 'FLAVOUR_ENHANCER', 1, 'Synergistic combination of GMP and IMP found in instant noodles, seasoning powders, and savory snacks.'),

    -- ---- Sweeteners (E950 - E968) ------------------------------------------
    ('e950_acesulfame_k', 'Acesulfame K', 'E950', 'SWEETENER', 1, 'Zero-calorie high-intensity artificial sweetener, 200 times sweeter than sucrose. Heat-stable for cooking.'),
    ('e951_aspartame', 'Aspartame', 'E951', 'SWEETENER', 2, 'Low-calorie high-intensity sweetener. Carries mandatory label warning for individuals with phenylketonuria (PKU).'),
    ('e952_cyclamate', 'Cyclamate', 'E952', 'SWEETENER', 2, 'Synthetic sweetener 30-50 times sweeter than sugar; used in blends with saccharin.'),
    ('e953_isomalt', 'Isomalt', 'E953', 'SWEETENER', 1, 'Sugar alcohol made from beet sugar; does not promote tooth decay and yields crystal-clear hard candies.'),
    ('e954_saccharin', 'Saccharin', 'E954', 'SWEETENER', 1, 'Oldest zero-calorie synthetic sweetener; 300 to 400 times sweeter than sugar with a slightly bitter metallic aftertaste.'),
    ('e955_sucralose', 'Sucralose', 'E955', 'SWEETENER', 1, 'Splenda; chlorinated sugar derivative 600 times sweeter than sugar with outstanding heat and shelf stability.'),
    ('e960_steviol_glycosides', 'Steviol Glycosides', 'E960', 'SWEETENER', 1, 'High-purity natural calorie-free sweetener extracted from Stevia rebaudiana leaves.'),
    ('e965_maltitol', 'Maltitol', 'E965', 'SWEETENER', 1, 'Polyol delivering 90% of sugar sweetness with half the calories; prevents crystal formation in chocolate.'),
    ('e967_xylitol', 'Xylitol', 'E967', 'SWEETENER', 1, 'Birch bark sugar alcohol proven to actively inhibit tooth decay bacteria in chewing gums and dental lozenges.'),
    ('e968_erythritol', 'Erythritol', 'E968', 'SWEETENER', 1, 'Naturally fermented four-carbon polyol with zero glycemic index and high digestive tolerance.'),

    -- ---- Miscellaneous, Glazing & Enzymes (E901 - E1520) -------------------
    ('e901_beeswax', 'Beeswax', 'E901', 'STABILISER', 1, 'Natural wax produced by honey bees; provides protective glazing on chocolate confections and citrus fruits.'),
    ('e903_carnauba_wax', 'Carnauba Wax', 'E903', 'STABILISER', 1, 'Hard vegetable wax extracted from Copernicia prunifera palm fronds; high-gloss polish on chewing gum and jelly beans.'),
    ('e904_shellac', 'Shellac', 'E904', 'STABILISER', 1, 'Natural resin secretion of the female lac insect; coating agent for candies, chocolates, and vitamin pills.'),
    ('e1105_lysozyme', 'Lysozyme', 'E1105', 'PRESERVATIVE', 3, 'Natural antimicrobial enzyme extracted from egg whites. Regulated major allergen: triggers allergic reactions in individuals allergic to poultry eggs.'),
    ('e1520_propylene_glycol', 'Propylene Glycol', 'E1520', 'EMULSIFIER', 1, 'Synthetic moisture-preserving liquid carrying food flavorings, color solutions, and bakery glazes.')
),
inserted_ingredients AS (
    INSERT INTO kb.ingredients (slug, canonical_name, ingredient_type, explanation)
    SELECT r.slug, r.canonical_name, 'additive'::kb.ingredient_type, r.explanation
      FROM raw_additives r
    ON CONFLICT (slug) DO UPDATE
    SET canonical_name = EXCLUDED.canonical_name,
        explanation    = EXCLUDED.explanation,
        updated_at     = now()
    RETURNING ingredient_id, slug
)
INSERT INTO kb.additive_details (ingredient_id, e_number, additive_category_id, concern_level)
SELECT ii.ingredient_id,
       r.e_number,
       ac.additive_category_id,
       r.concern
  FROM inserted_ingredients ii
  JOIN raw_additives r ON r.slug = ii.slug
  JOIN kb.additive_categories ac ON ac.code = r.cat_code
ON CONFLICT (ingredient_id) DO UPDATE
SET e_number             = EXCLUDED.e_number,
    additive_category_id = EXCLUDED.additive_category_id,
    concern_level        = EXCLUDED.concern_level;
