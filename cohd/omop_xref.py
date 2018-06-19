import requests
from numpy import argsort

# OXO API configuration
_URL_OXO_SEARCH = u'https://www.ebi.ac.uk/spot/oxo/api/search'
_OXO_OMOP_MAPPING_TARGETS = [u'ICD9CM', u'ICD10CM', u'SNOMEDCT', u'MeSH']
_OXO_OMOP_VOCABULARIES = [u'ICD9CM', u'ICD10CM', u'SNOMED', u'MeSH']
_OXO_PREFIX_TO_OMOP_VOCAB = {
    u'ICD9CM': u'ICD9CM',
    u'ICD10CM': u'ICD10CM',
    u'SNOMEDCT': u'SNOMED',
    u'MeSH': u'MeSH'
}
_OMOP_VOCAB_TO_OXO_PREFIX = {
    u'ICD9CM': u'ICD9CM',
    u'ICD10CM': u'ICD10CM',
    u'SNOMED': u'SNOMEDCT',
    u'MeSH': u'MeSH'
}


def omop_vocab_to_oxo_prefix(vocab):
    """ Attempt to lookup the corresponding OxO prefix from the OMOP vocabulary ID

    Uses the mapping defined in _OMOP_VOCAB_TO_OXO_PREFIX, but if no mapping is found, returns the vocabulary

    :param vocab: string - OMOP vocabulary_id
    :return: string - OxO prefix
    """
    prefix = vocab
    if vocab in _OMOP_VOCAB_TO_OXO_PREFIX:
        prefix = _OMOP_VOCAB_TO_OXO_PREFIX[vocab]
    return prefix


def omop_concept_lookup(cur, concept_id):
    """ Look up concept info

    :param cur: SQL cursor
    :param concept_id: int - concept_id
    :return: row from concept table
    """
    sql = '''SELECT *
        FROM cohd.concept
        WHERE concept_id = %(concept_id)s;'''
    params = {'concept_id': concept_id}

    cur.execute(sql, params)
    return cur.fetchall()


def omop_map_to_standard(cur, concept_code, vocabulary_id=None):
    """ OMOP map from concept code to standard concept_id

    :param cur: sql cursor
    :param concept_code: String - source concept code
    :param vocabulary_id: String - source vocabulary (optional)
    :return: List of mappings to standard concept_id
    """
    sql = '''SELECT
                c1.concept_id AS source_concept_id, 
                c1.concept_code AS source_concept_code,
                c1.concept_name AS source_concept_name, 
                c1.vocabulary_id AS source_vocabulary_id, 
                c2.concept_id AS standard_concept_id, 
                c2.concept_name AS standard_concept_name,
                c2.domain_id AS standard_domain_id
            FROM concept c1
            JOIN concept_relationship cr ON c1.concept_id = cr.concept_id_1
            JOIN concept c2 ON cr.concept_id_2 = c2.concept_id
            WHERE c1.concept_code = %(concept_code)s AND relationship_id = 'Maps to'
        '''
    params = {'concept_code': concept_code}

    # Restrict by vocabulary_id if specified
    if vocabulary_id is not None:
        sql += "    AND c1.vocabulary_id = %(vocabulary_id)s"
        params['vocabulary_id'] = vocabulary_id

    sql += ';'

    cur.execute(sql, params)
    return cur.fetchall()


def omop_map_from_standard(cur, concept_id, vocabularies=None):
    """ OMOP map from standard concept_id to concept codes

    :param cur: sql cursor
    :param concept_id: int
    :param vocabularies: List of strings - target vocabularies to map to
    :return: List of mappings
    """
    sql = '''SELECT 
            c.concept_id,
            c.concept_code, 
            c.concept_name, 
            c.domain_id, 
            c.vocabulary_id, 
            c.concept_class_id,
            c.standard_concept
        FROM concept_relationship cr
        JOIN concept c ON cr.concept_id_1 = c.concept_id
        WHERE cr.concept_id_2 = %s AND relationship_id = 'Maps to'
        '''
    params = [concept_id]

    # Restrict by vocabulary_id if specified
    if vocabularies is not None and len(vocabularies) > 0:
        sql += '''    AND c.vocabulary_id IN (%s)
            ''' % ','.join(['%s' for _ in vocabularies])
        params += vocabularies

    sql += 'ORDER BY c.vocabulary_id ASC, c.concept_code ASC;'

    cur.execute(sql, params)
    results = cur.fetchall()
    if results == ():
        # If no results, return an empty list
        results = []

    return results


def oxo_search(ids, input_source=None, mapping_targets=[], distance=2):
    """ Wrapper to the OxO search method.

    :param ids: List of strings - CURIEs to search for
    :param input_source: String
    :param mapping_targets: List of strings - Prefixes for target ontologies
    :param distance: Integer [1-3], default=2
    :return: JSON return from /oxo/api/search
    """
    # Call OXO search to map from the CURIE to vocabularies that OMOP knows
    data = {
        "ids": ids,
        "inputSource": input_source,
        "mappingTarget": mapping_targets,
        "distance": distance
    }

    r = requests.post(url=_URL_OXO_SEARCH, data=data)
    json_return = r.json()
    return json_return


def xref_to_omop_standard_concept(cur, curie, distance=2):
    """ Map from external ontologies to OMOP

    Use OxO to map to OMOP vocabularies (ICD9, ICD10, SNOMEDCT, MeSH), then concept_relationship table to map to
    OMOP standard concept_id

    :param cur: SQL cursor
    :param curie: String - CURIE (e.g., 'DOID:8398')
    :param distance: Integer - OxO distance parameter [1-3], default=2
    :return: List of mappings
    """

    mappings = []
    total_distances = []

    # Call OxO to map to a vocabulary that OMOP knows
    j = oxo_search([curie], mapping_targets=_OXO_OMOP_MAPPING_TARGETS, distance=distance)
    search_result = j[u'_embedded'][u'searchResults'][0]
    mrl = search_result[u'mappingResponseList']

    # Map each OxO mapping using OMOP concept_relationship 'Maps_to'
    for mr in mrl:
        prefix, concept_code = mr[u'curie'].split(u':')

        # Determine the corresponding vocabulary_id
        vocabulary_id = _OXO_PREFIX_TO_OMOP_VOCAB.get(prefix)
        if prefix is None:
            # Conversion from OxO prefix to OMOP vocabulary_id is unknown
            continue

        # Map to the standard concept_id
        results = omop_map_to_standard(cur, concept_code, vocabulary_id)
        for result in results:
            omop_distance = int(result[u'source_concept_id'] != result[u'standard_concept_id'])
            oxo_distance = mr[u'distance']
            total_distance = omop_distance + oxo_distance
            mapping = {
                u'source_oxo_id': search_result[u'queryId'],
                u'source_oxo_label': search_result[u'label'],
                u'intermediate_oxo_id': mr[u'curie'],
                u'intermediate_oxo_label': mr[u'label'],
                u'oxo_distance': oxo_distance,
                u'omop_standard_concept_id': result[u'standard_concept_id'],
                u'omop_concept_name': result[u'standard_concept_name'],
                u'omop_domain_id': result[u'standard_domain_id'],
                u'omop_distance': omop_distance,
                u'total_distance': total_distance
            }
            mappings.append(mapping)
            total_distances.append(total_distance)

    # Sort the list of mappings by total distance
    mappings_sorted = [mappings[i] for i in argsort(total_distances)]
    return mappings_sorted


def xref_from_omop_standard_concept(cur, concept_id, mapping_targets=[], distance=2):
    """ Map from OMOP to external ontologies

    Use OMOP's concept_relationship table to map OMOP standard concept_ids to vocabularies supported in OxO
    (ICD9, ICD10, SNOMEDCT, MeSH), then use OxO to map to other ontologies

    :param cur: SQL cursor
    :param concept_id: int OMOP standard concept_id
    :param mapping_targets: List of string - target ontology prefixes
    :param distance: OxO distance
    :return: List of mappings
    """
    curies = []
    mappings = []
    search_results = []
    total_distances = []

    # Get concept ID info
    source_info = omop_concept_lookup(cur, concept_id)
    if len(source_info) == 0:
        # concept_id not found, return empty results
        return []
    source_info = source_info[0]

    # Map to compatible vocabularies (ICD9CM, ICD10CM, MeSH, and SNOMED)
    omop_mappings = omop_map_from_standard(cur, concept_id, _OXO_OMOP_VOCABULARIES)
    found_source = False
    for omop_mapping in omop_mappings:
        prefix = omop_vocab_to_oxo_prefix(omop_mapping[u'vocabulary_id'])
        curie = prefix + ':' + omop_mapping[u'concept_code']
        curies.append(curie)

        # Check if the source concept is included in the mappings
        found_source = found_source or (omop_mapping[u'concept_id'] == source_info[u'concept_id'])

    # Add the source concept definition if not already in OMOP mappings (e.g., source concept is not a standard concept)
    if not found_source and source_info[u'vocabulary_id'] in _OMOP_VOCAB_TO_OXO_PREFIX:
        prefix = omop_vocab_to_oxo_prefix(source_info[u'vocabulary_id'])
        curie = prefix + ':' + source_info[u'concept_code']
        curies.append(curie)
        omop_mappings.append(source_info)

    # Call OxO to map to a vocabulary that OMOP knows
    if len(curies) > 0:
        j = oxo_search(curies, mapping_targets=mapping_targets, distance=distance)
        search_results = j[u'_embedded'][u'searchResults']

    # Combine OxO mappings with OMOP mappings
    for i, search_result in enumerate(search_results):
        mrl = search_result[u'mappingResponseList']

        if len(mrl) == 0:
            continue

        # Add info from OMOP mapping to the search result
        omop_mapping = omop_mappings[i]
        omop_distance = int(omop_mapping[u'concept_id'] != concept_id)

        for mr in mrl:
            oxo_distance = mr[u'distance']
            total_distance = omop_distance + oxo_distance
            mapping = {
                u'source_omop_concept_id': concept_id,
                u'source_omop_concept_name': source_info[u'concept_name'],
                u'source_omop_vocabulary_id': source_info[u'vocabulary_id'],
                u'source_omop_concept_code': source_info[u'concept_code'],
                u'intermediate_omop_concept_id': omop_mapping[u'concept_id'],
                u'intermediate_omop_vocabulary_id': omop_mapping[u'vocabulary_id'],
                u'intermediate_omop_concept_code': omop_mapping[u'concept_code'],
                u'intermediate_omop_concept_name': omop_mapping[u'concept_name'],
                u'omop_distance': omop_distance,
                u'intermediate_oxo_curie': search_result[u'curie'],
                u'intermediate_oxo_label': search_result[u'label'],
                u'target_curie': mr[u'curie'],
                u'target_label': mr[u'label'],
                u'oxo_distance': oxo_distance,
                u'total_distance': total_distance
            }
            mappings.append(mapping)
            total_distances.append(total_distance)

    # sort the mappings by total distance
    mappings_sorted = [mappings[i] for i in argsort(total_distances)]
    return mappings_sorted


