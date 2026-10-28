// Executing organisation for the staff console; no LLM chooses it either.
// SUPERVISING_COMMUNE is resolved by the database to the citizen's commune.
x.organisation={ROAD_DAMAGE:'SUPERVISING_COMMUNE',WASTE:'SUPERVISING_COMMUNE',STREET_LIGHTING:'STEG',WATER_LEAK:'SONEDE'}[x.vision.category]||null;
