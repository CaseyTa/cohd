import pymysql
from flask import jsonify
from scipy.stats import chisquare
from numpy import argsort
from omop_xref import xref_to_omop_standard_concept, omop_map_to_standard, omop_map_from_standard, \
    xref_from_omop_standard_concept

# Configuration
# log-in credentials for database
CONFIG_FILE = u"cohd_mysql.cnf"
DEFAULT_DATASET_ID = 1

# OXO API configuration
URL_OXO_SEARCH = u'https://www.ebi.ac.uk/spot/oxo/api/search'
_DEFAULT_OXO_DISTANCE = 2
DEFAULT_OXO_MAPPING_TARGETS = ["ICD9CM", "ICD10CM", "SNOMEDCT", "MeSH"]


def _get_arg_datset_id(args):
    dataset_id = args.get(u'dataset_id')
    if dataset_id is None or dataset_id.isspace() or not dataset_id.strip().isdigit():
        dataset_id = DEFAULT_DATASET_ID
    else:
        dataset_id = int(dataset_id.strip())

    return dataset_id


def query_db(service, method, args):

    print u"Connecting to the MySQL API..."

    # Connect to MySQL database
    print u"Connecting to MySQL database"

    conn = pymysql.connect(read_default_file=CONFIG_FILE,
                           charset=u'utf8mb4',
                           cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()

    json_return = []

    query = args.get(u'q')

    print u"Service: ", service
    print u"Method: ", method
    print u"Query: ", query

    if service == u'metadata':
        # The datasets in the COHD database
        # endpoint: /api/v1/query?service=metadata&meta=datasets
        if method == u'datasets':
            sql = '''SELECT * 
                FROM cohd.dataset;'''
            cur.execute(sql)
            json_return = cur.fetchall()

        # The number of concepts in each domain
        # endpoint: /api/v1/query?service=metadata&meta=domainCounts&dataset_id=1
        elif method == u'domainCounts':
            dataset_id = _get_arg_datset_id(args)
            sql = '''SELECT * 
                FROM cohd.domain_concept_counts 
                WHERE dataset_id=%(dataset_id)s;'''
            params = {'dataset_id': dataset_id}
            cur.execute(sql, params)
            json_return = cur.fetchall()

        # The number of pairs of concepts in each pair of domains
        # endpoint: /api/v1/query?service=metadata&meta=domainPairCounts&dataset_id=1
        elif method == u'domainPairCounts':
            dataset_id = _get_arg_datset_id(args)
            sql = '''SELECT * 
                FROM cohd.domain_pair_concept_counts 
                WHERE dataset_id=%(dataset_id)s;'''
            params = {'dataset_id': dataset_id}
            cur.execute(sql, params)
            json_return = cur.fetchall()

        # The number of patients in the dataset
        # endpoint: /api/v1/query?service=metadata&meta=patientCount&dataset_id=1
        elif method == u'patientCount':
            dataset_id = _get_arg_datset_id(args)
            sql = '''SELECT * 
                FROM cohd.patient_count 
                WHERE dataset_id=%(dataset_id)s;'''
            params = {'dataset_id': dataset_id}
            cur.execute(sql, params)
            json_return = cur.fetchall()

    elif service == u'omop':
        # Find concept_ids and concept_names that are similar to the query
        # e.g. /api/v1/query?service=omop&meta=findConceptIDs&q=cancer
        if method == u'findConceptIDs':
            # Check query parameter
            if query is None or query == [u''] or query.isspace():
                return 'q parameter is missing', 400

            dataset_id = _get_arg_datset_id(args)

            sql = '''SELECT c.concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, concept_code,
                    IFNULL(concept_count, 0E0) AS concept_count
                FROM cohd.concept c
                LEFT JOIN cohd.concept_counts cc ON cc.concept_id = c.concept_id 
                WHERE concept_name like %(like_query)s AND standard_concept = 'S' 
                    AND ((cc.dataset_id = %(dataset_id)s) OR (cc.dataset_id IS NULL)) {domain_filter} 
                ORDER BY cc.concept_count DESC
                LIMIT 1000;'''
            params = {
                'like_query': '%' + query + '%',
                'dataset_id': dataset_id,
                'query': query
            }

            domain_id = args.get(u'domain')
            if domain_id is None or domain_id == [u''] or domain_id.isspace():
                domain_filter = ''
            else:
                domain_filter = 'AND domain_id = %(domain_id)s'
                params['domain_id'] = domain_id
            sql = sql.format(domain_filter=domain_filter)

            cur.execute(sql, params)
            json_return = cur.fetchall()

        # Looks up concepts for a list of concept_ids
        # e.g. /api/v1/query?service=omop&meta=concepts&q=4196636,437643
        elif method == u'concepts':
            # Check query parameter
            if query is None or query == [u''] or query.isspace():
                return u'q parameter is missing', 400
            for concept_id in query.split(','):
                if not concept_id.strip().isdigit():
                    return u'Error in q: concept_ids should be integers', 400

            # Convert query paramter to a list of concept ids
            concept_ids = [int(x.strip()) for x in query.split(',')]

            sql = '''SELECT concept_id, concept_name, domain_id, vocabulary_id, concept_class_id, concept_code 
                FROM cohd.concept
                WHERE concept_id IN (%s);''' % ','.join(['%s' for _ in concept_ids])

            cur.execute(sql, concept_ids)
            json_return = cur.fetchall()

        # Find concept_ids and concept_names that are similar to the query
        # e.g. /api/v1/query?service=omop&meta=mapToStandardConceptID&concept_code=715.3&vocabulary_id=ICD9CM
        elif method == u'mapToStandardConceptID':
            # Check concept_code parameter
            concept_code = args.get(u'concept_code')
            if concept_code is None or concept_code == [u''] or concept_code.isspace():
                return u'No concept_code was specified', 400

            # Check vocabulary_id parameter
            vocabulary_id = args.get(u'vocabulary_id')
            if vocabulary_id is None or vocabulary_id == [u''] or vocabulary_id.isspace():
                vocabulary_id = None

            # Map
            json_return = omop_map_to_standard(cur, concept_code, vocabulary_id)

        # Find concept_ids and concept_names that are similar to the query
        # e.g. /api/v1/query?service=omop&meta=mapFromStandardConceptID&concept_code=715.3&vocabulary_id=ICD9CM
        elif method == u'mapFromStandardConceptID':
            # Get concept_id parameter
            concept_id = args.get(u'concept_id')
            if concept_id is None or concept_id == [u'']:
                return u'No concept_id was specified', 400

            # Get vocabulary_id parameter
            vocabulary_id = args.get(u'vocabulary_id')
            if vocabulary_id is not None:
                if vocabulary_id == [u'']:
                    vocabulary_id = None
                else:
                    vocabulary_id = [x.strip() for x in vocabulary_id.split(u',')]

            # Map
            json_return = omop_map_from_standard(cur, concept_id, vocabulary_id)

        # List of vocabularies
        # e.g. /api/v1/query?service=omop&meta=vocabularies
        elif method == u'vocabularies':
            sql = '''SELECT DISTINCT vocabulary_id FROM concept;'''
            cur.execute(sql)
            json_return = cur.fetchall()

        # Cross reference to OMOP using OXO service
        # e.g. /api/v1/query?service=omop&meta=xrefToOMOP?curie=DOID:8398&distance=1
        elif method == u'xrefToOMOP':
            # curie is required
            curie = args.get(u'curie')
            if curie is None or curie == [u'']:
                return u'No curie was specified', 400

            distance = args.get(u'distance')
            if distance is None or distance == [u'']:
                distance = _DEFAULT_OXO_DISTANCE

            json_return = xref_to_omop_standard_concept(cur, curie, distance)

        # Cross reference from OMOP using OXO service
        # e.g. /api/v1/query?service=omop&meta=xrefFromOMOP?concept_id=192855&distance=1
        elif method == u'xrefFromOMOP':
            # curie is required
            concept_id = args.get(u'concept_id')
            if concept_id is None or concept_id == [u''] or not concept_id.strip().isdigit():
                return u'No curie was specified', 400
            else:
                concept_id = int(concept_id)

            # get mapping_targets, if specified
            mapping_targets = args.get(u'mapping_targets')
            if mapping_targets is None or mapping_targets == [u'']:
                mapping_targets = []
            else:
                # convert to list of mapping targets
                mapping_targets = [x.strip() for x in mapping_targets.split(',')]

            # get distance, if specified
            distance = args.get(u'distance')
            if distance is None or distance == [u'']:
                distance = _DEFAULT_OXO_DISTANCE

            json_return = xref_from_omop_standard_concept(cur, concept_id, mapping_targets, distance)

    elif service == u'frequencies':
        # Looks up observed clinical frequencies for a comma separated list of concepts
        # e.g. /api/v1/query?service=frequencies&meta=singleConceptFreq&dataset_id=1&q=4196636,437643
        if method == u'singleConceptFreq':
            dataset_id = _get_arg_datset_id(args)

            # Check concept_ids parameter
            if query is None or query == [u''] or query.isspace():
                return u'q parameter is missing', 400

            for x in query.split(u','):
                if not x.strip().isdigit():
                    return u'Error in q: concept_ids should be integers', 400

            # Convert query parameter to list of concept IDs
            concept_ids = [int(x.strip()) for x in query.split(u',') if x.strip().isdigit()]

            sql = '''SELECT 
                    cc.dataset_id,
                    cc.concept_id,
                    cc.concept_count,
                    cc.concept_count / (pc.count + 0E0) AS concept_frequency
                FROM cohd.concept_counts cc
                JOIN cohd.patient_count pc ON cc.dataset_id = pc.dataset_id
                WHERE cc.dataset_id = %s AND concept_id IN ({concepts});'''.format(
                concepts=','.join(['%s' for _ in concept_ids]))
            params = [dataset_id] + concept_ids

            cur.execute(sql, params)
            json_return = cur.fetchall()

        # Looks up observed clinical frequencies for a comma separated list of concepts
        # e.g. /api/v1/query?service=frequencies&meta=pairedConceptFreq&dataset_id=1&q=4196636,437643
        elif method == u'pairedConceptFreq':
            dataset_id = _get_arg_datset_id(args)

            # Check q parameter
            if query is None or query == [u''] or query.isspace():
                return u'q parameter is missing', 400

            # q parameter should be 2 concept_ids separated by comma
            qs = query.split(u',')
            if len(qs) != 2 or not qs[0].strip().isdigit() or not qs[1].strip().isdigit():
                return u'Error in q: should be two concept IDs, e.g., 4196636,437643', 400

            concept_id_1 = int(qs[0])
            concept_id_2 = int(qs[1])
            sql = '''SELECT 
                    cpc.dataset_id,
                    cpc.concept_id_1,
                    cpc.concept_id_2,
                    cpc.concept_count,
                    cpc.concept_count / (pc.count + 0E0) AS concept_frequency
                FROM cohd.concept_pair_counts cpc
                JOIN cohd.patient_count pc ON pc.dataset_id = cpc.dataset_id
                WHERE cpc.dataset_id = %(dataset_id)s AND  
                    ((concept_id_1 = %(concept_id_1)s AND concept_id_2 = %(concept_id_2)s) OR 
                    (concept_id_1 = %(concept_id_2)s AND concept_id_2 = %(concept_id_1)s));'''
            params = {
                'dataset_id': dataset_id,
                'concept_id_1': concept_id_1,
                'concept_id_2': concept_id_2
            }

            cur.execute(sql, params)
            json_return = cur.fetchall()

        # Looks up observed clinical frequencies of all pairs of concepts given a concept id
        # e.g. /api/v1/query?service=frequencies&meta=associatedConceptFreq&dataset_id=1&q=4196636
        elif method == u'associatedConceptFreq':
            dataset_id = _get_arg_datset_id(args)

            # Check q parameter
            if query is None or query == [u''] or query.isspace():
                return u'q parameter is missing', 400

            if not query.strip().isdigit():
                return u'Error in q: concept_id should be an integer'

            concept_id = int(query)

            sql = '''SELECT *
                FROM
                    ((SELECT 
                        cpc.dataset_id, 
                        cpc.concept_id_1 AS concept_id,
                        cpc.concept_id_2 AS associated_concept_id,                    
                        cpc.concept_count, 
                        cpc.concept_count / (pc.count + 0E0) AS concept_frequency,
                        c.concept_name AS associated_concept_name, 
                        c.domain_id AS associated_domain_id
                    FROM cohd.concept_pair_counts cpc
                    JOIN cohd.concept c ON concept_id_2 = c.concept_id     
                    JOIN cohd.patient_count pc ON cpc.dataset_id = pc.dataset_id          
                    WHERE cpc.dataset_id = %(dataset_id)s AND concept_id_1 = %(concept_id)s)
                    UNION
                    (SELECT 
                        cpc.dataset_id, 
                        cpc.concept_id_2 AS concept_id,
                        cpc.concept_id_1 AS associated_concept_id,                    
                        cpc.concept_count, 
                        cpc.concept_count / (pc.count + 0E0) AS concept_frequency,
                        c.concept_name AS associated_concept_name, 
                        c.domain_id AS associated_domain_id
                    FROM cohd.concept_pair_counts cpc
                    JOIN cohd.concept c ON concept_id_1 = c.concept_id             
                    JOIN cohd.patient_count pc ON cpc.dataset_id = pc.dataset_id      
                    WHERE cpc.dataset_id = %(dataset_id)s AND concept_id_2 = %(concept_id)s)) x
                ORDER BY concept_count DESC;'''
            params = {
                'dataset_id': dataset_id,
                'concept_id': concept_id
            }

            cur.execute(sql, params)
            json_return = cur.fetchall()

        # Looks up observed clinical frequencies of all pairs of concepts given a concept id restricted by domain of the
        # associated concept_id
        # e.g. /api/v1/query?service=frequencies&meta=associatedConceptDomainFreq&dataset_id=1&concept_id=4196636&domain=Procedure
        elif method == u'associatedConceptDomainFreq':
            dataset_id = _get_arg_datset_id(args)
            concept_id = args.get(u'concept_id')
            domain_id = args.get(u'domain')

            if concept_id is None or concept_id == [u''] or concept_id.isspace():
                return u'No concept_id selected', 400

            if domain_id is None or domain_id == [u''] or domain_id.isspace():
                return u'No domain selected', 400

            if not concept_id.strip().isdigit():
                return u'concept_id should be numeric', 400

            concept_id = int(concept_id)

            sql = '''SELECT *
                FROM
                    ((SELECT 
                        cpc.dataset_id, 
                        cpc.concept_id_1 AS concept_id,
                        cpc.concept_id_2 AS associated_concept_id,                    
                        cpc.concept_count, 
                        cpc.concept_count / (pc.count + 0E0) AS concept_frequency,
                        c.concept_name AS associated_concept_name, 
                        c.domain_id AS associated_domain_id
                    FROM cohd.concept_pair_counts cpc
                    JOIN cohd.concept c ON concept_id_2 = c.concept_id     
                    JOIN cohd.patient_count pc ON cpc.dataset_id = pc.dataset_id          
                    WHERE cpc.dataset_id = %(dataset_id)s AND concept_id_1 = %(concept_id)s
                        AND c.domain_id = %(domain_id)s)
                    UNION
                    (SELECT 
                        cpc.dataset_id, 
                        cpc.concept_id_2 AS concept_id,
                        cpc.concept_id_1 AS associated_concept_id,                    
                        cpc.concept_count, 
                        cpc.concept_count / (pc.count + 0E0) AS concept_frequency,
                        c.concept_name AS associated_concept_name, 
                        c.domain_id AS associated_domain_id
                    FROM cohd.concept_pair_counts cpc
                    JOIN cohd.concept c ON concept_id_1 = c.concept_id             
                    JOIN cohd.patient_count pc ON cpc.dataset_id = pc.dataset_id      
                    WHERE cpc.dataset_id = %(dataset_id)s AND concept_id_2 = %(concept_id)s
                        AND c.domain_id = %(domain_id)s)) x
                ORDER BY concept_count DESC;'''
            params = {
                'dataset_id': dataset_id,
                'concept_id': concept_id,
                'domain_id': domain_id
            }

            cur.execute(sql, params)
            json_return = cur.fetchall()

        # Returns most common single concept frequencies
        # e.g. /api/v1/query?service=frequencies&meta=mostFrequentConcept&dataset_id=1&q=100
        elif method == u'mostFrequentConcepts':
            dataset_id = _get_arg_datset_id(args)

            # Check q parameter (limit)
            if query is None or query == [u''] or query.isspace() or not query.strip().isdigit():
                limit_n = 100
            else:
                limit_n = int(query)

            params = {
                'dataset_id': dataset_id,
                'limit_n': limit_n
            }
            sql = '''SELECT cc.dataset_id, 
                        cc.concept_id, 
                        cc.concept_count, 
                        cc.concept_count / (pc.count + 0E0) AS concept_frequency,
                        c.domain_id, c.concept_name 
                    FROM cohd.concept_counts cc
                    JOIN cohd.concept c ON cc.concept_id = c.concept_id
                    JOIN cohd.patient_count pc ON cc.dataset_id = pc.dataset_id
                    WHERE cc.dataset_id = %(dataset_id)s
                    '''

            # Check domain parameter
            domain_id = args.get(u'domain')
            if domain_id is not None and domain_id != [u''] and not domain_id.isspace():
                sql += '''    AND c.domain_id = %(domain_id)s
                    '''
                params['domain_id'] = domain_id

            sql += '''ORDER BY concept_count DESC 
                    LIMIT %(limit_n)s;'''

            cur.execute(sql, params)
            json_return = cur.fetchall()

    elif service == u'association':
        # Returns chi-square between pairs of concepts
        # e.g. /api/v1/query?service=association&meta=chiSquare&dataset_id=1&concept_id_1=192855&concept_id_2=2008271
        if method == u'chiSquare':
            # Get non-required parameters
            dataset_id = _get_arg_datset_id(args)
            concept_id_2 = args.get(u'concept_id_2')
            domain_id = args.get(u'domain')

            # concept_id_1 is required
            concept_id_1 = args.get(u'concept_id_1')
            if concept_id_1 is None or concept_id_1 == [u''] or not concept_id_1.strip().isdigit():
                return u'No concept_id_1 selected', 400
            concept_id_1 = int(concept_id_1)

            if concept_id_2 is not None and concept_id_2.strip().isdigit():
                # concept_id_2 is specified, only return the chi-square for the pair (concept_id_1, concept_id_2)
                concept_id_2 = int(concept_id_2)
                sql = '''SELECT 
                        cp.dataset_id, 
                        cp.concept_id_1, 
                        cp.concept_id_2,
                        cp.concept_count AS concept_pair_count,
                        c1.concept_count AS concept_count_1,
                        c2.concept_count AS concept_count_2,
                        pc.count AS patient_count
                    FROM cohd.concept_pair_counts cp
                    JOIN cohd.concept_counts c1 ON cp.concept_id_1 = c1.concept_id
                    JOIN cohd.concept_counts c2 ON cp.concept_id_2 = c2.concept_id
                    JOIN cohd.patient_count pc ON cp.dataset_id = pc.dataset_id
                    WHERE cp.dataset_id = %(dataset_id)s 
                        AND c1.dataset_id = %(dataset_id)s 
                        AND c2.dataset_id = %(dataset_id)s
                        AND cp.concept_id_1 IN (%(concept_id_1)s, %(concept_id_2)s)
                        AND cp.concept_id_2 IN (%(concept_id_1)s, %(concept_id_2)s);'''
                params = {
                    'dataset_id': dataset_id,
                    'concept_id_1': concept_id_1,
                    'concept_id_2': concept_id_2
                }

            else:
                # If concept_id_2 is not specified, get results for all pairs that include concept_id_1
                concept_id_2 = None
                sql = '''SELECT * 
                    FROM
                        ((SELECT 
                            cp.dataset_id, 
                            cp.concept_id_1, 
                            cp.concept_id_2,
                            cp.concept_count AS concept_pair_count,
                            c1.concept_count AS concept_count_1,
                            c2.concept_count AS concept_count_2,
                            pc.count AS patient_count,
                            c.concept_name AS concept_2_name, 
                            c.domain_id AS concept_2_domain
                        FROM cohd.concept_pair_counts cp
                        JOIN cohd.concept_counts c1 ON cp.concept_id_1 = c1.concept_id
                        JOIN cohd.concept_counts c2 ON cp.concept_id_2 = c2.concept_id
                        JOIN cohd.patient_count pc ON cp.dataset_id = pc.dataset_id
                        JOIN cohd.concept c ON cp.concept_id_2 = c.concept_id
                        WHERE cp.dataset_id = %(dataset_id)s 
                            AND c1.dataset_id = %(dataset_id)s 
                            AND c2.dataset_id = %(dataset_id)s
                            AND cp.concept_id_1 = %(concept_id_1)s 
                            {domain_filter})
                        UNION
                        (SELECT 
                            cp.dataset_id, 
                            cp.concept_id_2 AS concept_id_1, 
                            cp.concept_id_1 AS concept_id_2,
                            cp.concept_count AS concept_pair_count,
                            c2.concept_count AS concept_count_1,
                            c1.concept_count AS concept_count_2,
                            pc.count AS patient_count,
                            c.concept_name AS concept_2_name, 
                            c.domain_id AS concept_2_domain
                        FROM cohd.concept_pair_counts cp
                        JOIN cohd.concept_counts c1 ON cp.concept_id_1 = c1.concept_id
                        JOIN cohd.concept_counts c2 ON cp.concept_id_2 = c2.concept_id
                        JOIN cohd.patient_count pc ON cp.dataset_id = pc.dataset_id
                        JOIN cohd.concept c ON cp.concept_id_1 = c.concept_id
                        WHERE cp.dataset_id = %(dataset_id)s 
                            AND c1.dataset_id = %(dataset_id)s 
                            AND c2.dataset_id = %(dataset_id)s
                            AND cp.concept_id_2 = %(concept_id_1)s 
                            {domain_filter})) x;'''
                params = {
                    'dataset_id': dataset_id,
                    'concept_id_1': concept_id_1
                }

                if domain_id is not None and not domain_id == [u'']:
                    domain_filter = 'AND c.domain_id = %(domain_id)s'
                    params['domain_id'] = domain_id
                else:
                    domain_filter = ''
                sql = sql.format(domain_filter=domain_filter)

            cur.execute(sql, params)
            results = cur.fetchall()

            # Calculate the p-value using chi-square distribution with 1 degree of freedom
            chi_squares = []
            for r in results:
                # Get observed counts
                cpc = float(r[u'concept_pair_count'])
                c1 = float(r[u'concept_count_1'])
                c2 = float(r[u'concept_count_2'])
                pts = float(r[u'patient_count'])
                neg = pts - c1 - c2 + cpc

                # Create the observed and expected RxC tables and perform chi-square
                o = [neg, c1 - cpc, c2 - cpc, cpc]
                e = [(pts - c1) * (pts - c2) / pts, c1 * (pts - c2) / pts, c2 * (pts - c1) / pts, c1 * c2 / pts]
                cs = chisquare(o, e, 2)
                new_r = {
                    u'dataset_id': r[u'dataset_id'],
                    u'concept_id_1': r[u'concept_id_1'],
                    u'concept_id_2': r[u'concept_id_2'],
                    u'chi_square': cs.statistic,
                    u'p-value': cs.pvalue
                }
                if concept_id_2 is None:
                    new_r[u'concept_2_name'] = r[u'concept_2_name']
                    new_r[u'concept_2_domain'] = r[u'concept_2_domain']

                json_return.append(new_r)
                chi_squares.append(cs.statistic)

            # Sort results by chi-square
            json_return = [json_return[i] for i in list(reversed(argsort(chi_squares)))]

        # Returns ratio of observed to expected frequency between pairs of concepts
        # e.g. /api/v1/query?service=association&meta=obsExpRatio&dataset_id=1&concept_id_1=192855&concept_id_2=2008271
        elif method == u'obsExpRatio':
            # Get non-required parameters
            dataset_id = _get_arg_datset_id(args)
            concept_id_2 = args.get(u'concept_id_2')
            domain_id = args.get(u'domain')

            # concept_id_1 is required
            concept_id_1 = args.get(u'concept_id_1')
            if concept_id_1 is None or concept_id_1 == [u''] or not concept_id_1.strip().isdigit():
                return u'No concept_id_1 selected', 400

            if concept_id_2 is not None and concept_id_2.strip().isdigit():
                # concept_id_2 is specified, only return the results for the pair (concept_id_1, concept_id_2)
                sql = '''SELECT 
                        cp.dataset_id, 
                        cp.concept_id_1, 
                        cp.concept_id_2,
                        cp.concept_count AS observed_count,
                        c1.concept_count * c2.concept_count / (pc.count + 0E0) AS expected_count,
                        log(cp.concept_count * pc.count / (c1.concept_count * c2.concept_count + 0E0)) AS ln_ratio
                    FROM cohd.concept_pair_counts cp
                    JOIN cohd.concept_counts c1 ON cp.concept_id_1 = c1.concept_id
                    JOIN cohd.concept_counts c2 ON cp.concept_id_2 = c2.concept_id
                    JOIN cohd.patient_count pc ON cp.dataset_id = pc.dataset_id
                    WHERE cp.dataset_id = %(dataset_id)s 
                        AND c1.dataset_id = %(dataset_id)s 
                        AND c2.dataset_id = %(dataset_id)s
                        AND cp.concept_id_1 IN (%(concept_id_1)s, %(concept_id_2)s)
                        AND cp.concept_id_2 IN (%(concept_id_1)s, %(concept_id_2)s);'''
                params = {
                    'dataset_id': dataset_id,
                    'concept_id_1': concept_id_1,
                    'concept_id_2': int(concept_id_2)
                }

            else:
                # If concept_id_2 is not specified, get results for all pairs that include concept_id_1
                sql = '''SELECT * 
                    FROM
                        ((SELECT 
                            cp.dataset_id, 
                            cp.concept_id_1, 
                            cp.concept_id_2,
                            cp.concept_count AS observed_count,
                            c1.concept_count * c2.concept_count / (pc.count + 0E0) AS expected_count,
                            log(cp.concept_count * pc.count / (c1.concept_count * c2.concept_count + 0E0)) AS ln_ratio,
                            c.concept_name AS concept_2_name, 
                            c.domain_id AS concept_2_domain
                        FROM cohd.concept_pair_counts cp
                        JOIN cohd.concept_counts c1 ON cp.concept_id_1 = c1.concept_id
                        JOIN cohd.concept_counts c2 ON cp.concept_id_2 = c2.concept_id
                        JOIN cohd.patient_count pc ON cp.dataset_id = pc.dataset_id
                        JOIN cohd.concept c ON cp.concept_id_2 = c.concept_id
                        WHERE cp.dataset_id = %(dataset_id)s 
                            AND c1.dataset_id = %(dataset_id)s 
                            AND c2.dataset_id = %(dataset_id)s
                            AND cp.concept_id_1 = %(concept_id_1)s 
                            {domain_filter})
                        UNION
                        (SELECT 
                            cp.dataset_id, 
                            cp.concept_id_2 AS concept_id_1, 
                            cp.concept_id_1 AS concept_id_2,
                            cp.concept_count AS observed_count,
                            c1.concept_count * c2.concept_count / (pc.count + 0E0) AS expected_count,
                            log(cp.concept_count * pc.count / (c1.concept_count * c2.concept_count + 0E0)) AS ln_ratio,
                            c.concept_name AS concept_2_name, 
                            c.domain_id AS concept_2_domain
                        FROM cohd.concept_pair_counts cp
                        JOIN cohd.concept_counts c1 ON cp.concept_id_1 = c1.concept_id
                        JOIN cohd.concept_counts c2 ON cp.concept_id_2 = c2.concept_id
                        JOIN cohd.patient_count pc ON cp.dataset_id = pc.dataset_id
                        JOIN cohd.concept c ON cp.concept_id_1 = c.concept_id
                        WHERE cp.dataset_id = %(dataset_id)s 
                            AND c1.dataset_id = %(dataset_id)s 
                            AND c2.dataset_id = %(dataset_id)s
                            AND cp.concept_id_2 = %(concept_id_1)s 
                            {domain_filter})) x
                    ORDER BY ln_ratio DESC;'''
                params = {
                    'dataset_id': dataset_id,
                    'concept_id_1': concept_id_1,
                }

                if domain_id is not None and not domain_id == [u'']:
                    # Restrict the associated concept by domain
                    domain_filter = 'AND c.domain_id = %(domain_id)s'
                    params['domain_id'] = domain_id
                else:
                    # Unrestricted domain
                    domain_filter = ''
                sql = sql.format(domain_filter=domain_filter)

            cur.execute(sql, params)
            json_return = cur.fetchall()

        # Returns relative frequency between pairs of concepts
        # e.g. /api/v1/query?service=association&meta=relativeFrequency&dataset_id=1&concept_id_1=192855&concept_id_2=2008271
        elif method == u'relativeFrequency':
            # Get non-required parameters
            dataset_id = _get_arg_datset_id(args)
            concept_id_2 = args.get(u'concept_id_2')
            domain_id = args.get(u'domain')

            # concept_id_1 is required
            concept_id_1 = args.get(u'concept_id_1')
            if concept_id_1 is None or concept_id_1 == [u''] or not concept_id_1.strip().isdigit():
                return u'No concept_id_1 selected', 400

            if concept_id_2 is not None and concept_id_2.strip().isdigit():
                # concept_id_2 is specified, only return the results for the pair (concept_id_1, concept_id_2)
                sql = '''(SELECT
                        cp.dataset_id,
                        cp.concept_id_1,
                        cp.concept_id_2,
                        cp.concept_count AS concept_pair_count,
                        cc.concept_count AS concept_2_count,
                        cp.concept_count / (cc.concept_count + 0E0) AS relative_frequency
                    FROM cohd.concept_pair_counts cp
                    JOIN cohd.concept_counts cc ON cp.concept_id_2 = cc.concept_id
                    WHERE cp.dataset_id = %(dataset_id)s
                        AND cc.dataset_id = %(dataset_id)s
                        AND cp.concept_id_1 = %(concept_id_1)s
                        AND cp.concept_id_2 = %(concept_id_2)s)
                    UNION
                    (SELECT
                        cp.dataset_id,
                        cp.concept_id_2 AS concept_id_1,
                        cp.concept_id_1 AS concept_id_2,
                        cp.concept_count AS concept_pair_count,
                        cc.concept_count AS concept_2_count,
                        cp.concept_count / (cc.concept_count + 0E0) AS relative_frequency
                    FROM cohd.concept_pair_counts cp
                    JOIN cohd.concept_counts cc ON cp.concept_id_1 = cc.concept_id
                    WHERE cp.dataset_id = %(dataset_id)s
                        AND cc.dataset_id = %(dataset_id)s
                        AND cp.concept_id_1 = %(concept_id_2)s
                        AND cp.concept_id_2 = %(concept_id_1)s);'''
                params = {
                    'dataset_id': dataset_id,
                    'concept_id_1': concept_id_1,
                    'concept_id_2': int(concept_id_2)
                }

            else:
                # If concept_id_2 is not specified, get results for all pairs that include concept_id_1
                sql = '''SELECT *
                    FROM
                        ((SELECT
                            cp.dataset_id,
                            cp.concept_id_1,
                            cp.concept_id_2,
                            cp.concept_count AS concept_pair_count,
                            cc.concept_count AS concept_2_count,
                            cp.concept_count / (cc.concept_count + 0E0) AS relative_frequency,
                            c.concept_name AS concept_2_name,
                            c.domain_id AS concept_2_domain
                        FROM cohd.concept_pair_counts cp
                        JOIN cohd.concept_counts cc ON cp.concept_id_2 = cc.concept_id
                        JOIN cohd.concept c ON cp.concept_id_2 = c.concept_id
                        WHERE cp.dataset_id = %(dataset_id)s
                            AND cc.dataset_id = %(dataset_id)s
                            AND cp.concept_id_1 = %(concept_id_1)s
                            {domain_filter})
                        UNION
                        (SELECT
                            cp.dataset_id,
                            cp.concept_id_2 AS concept_id_1,
                            cp.concept_id_1 AS concept_id_2,
                            cp.concept_count AS concept_pair_count,
                            cc.concept_count AS concept_2_count,
                            cp.concept_count / (cc.concept_count + 0E0) AS relative_frequency,
                            c.concept_name AS concept_2_name,
                            c.domain_id AS concept_2_domain
                        FROM cohd.concept_pair_counts cp
                        JOIN cohd.concept_counts cc ON cp.concept_id_1 = cc.concept_id
                        JOIN cohd.concept c ON cp.concept_id_1 = c.concept_id
                        WHERE cp.dataset_id = %(dataset_id)s
                            AND cc.dataset_id = %(dataset_id)s
                            AND cp.concept_id_2 = %(concept_id_1)s
                            {domain_filter})) x
                    ORDER BY relative_frequency DESC;'''
                params = {
                    'dataset_id': dataset_id,
                    'concept_id_1': concept_id_1,
                }

                if domain_id is not None and not domain_id == [u'']:
                    # Restrict the associated concept by domain
                    domain_filter = 'AND c.domain_id = %(domain_id)s'
                    params['domain_id'] = domain_id
                else:
                    # Unrestricted domain
                    domain_filter = ''
                sql = sql.format(domain_filter=domain_filter)

            cur.execute(sql, params)
            json_return = cur.fetchall()

    print cur._executed
    # print(json_return)

    cur.close()
    conn.close()

    json_return = {u"results": json_return}
    json_return = jsonify(json_return)

    return json_return
