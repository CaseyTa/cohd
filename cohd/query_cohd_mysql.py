import pymysql
from flask import jsonify

# log-in credentials for database
CONFIG_FILE = u"cohd_mysql.cnf"

def query_db(service, method, query=False, cache=False):

    print u"Connecting to the MySQL API..."

    # Connect to MySQL database
    print u"Connecting to MySQL database"

    conn = pymysql.connect(read_default_file=CONFIG_FILE,
                charset=u'utf8mb4',
                cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()

    table_suffix = u""
    json_return = []

    print u"Service: ", service
    print u"Method: ", method
    print u"Query: ", query

    if service == u'omop':
        # Find concept_ids and concept_names that are similar to the query
        # e.g. /api/v1/query?service=omop&meta=findConceptIDs&q=cancer
        if method == u'findConceptIDs':
            sql = '''select concept_id, concept_name
                from cohd.concept
                where concept_name like "%{query}%"
                -- order by cohd.levenshtein(lower("{query}"), lower(concept_name))
                limit 1000;'''.format(query=query)

            print sql

            cur.execute(sql)
            results = cur.fetchall()

            for result in results:
                json_return.append({
                    u'concept_id': result[u'concept_id'],
                    u'concept_name': result[u'concept_name']
                })

        # Looks up concepts for a list of concept_ids
        # e.g. /api/v1/query?service=omop&meta=concepts&q=4196636,437643
        elif method == u'concepts':
            if len(query.split(u',')) > 1:
                concept_ids = unicode(tuple([int(c) for c in query.split(u',') if c != u'None']))
                query_str = u"in"
            else:
                concept_ids = query
                query_str = u"="

            sql = u'''select *
                     from cohd.concept
                     where concept_id %s %s''' %(query_str, concept_ids)

            print u"RUNNING MYSQL QUERY..."
            cur.execute(sql)
            results = cur.fetchall()
            print u"...QUERY FINISHED."

            for result in results:
                json_return.append({
                    u"concept_id": result[u'concept_id'],
                    u"domain_id": result[u'domain_id'],
                    u"concept_name": result[u'concept_name']
                })

    elif service == u'frequencies':
        # Looks up observed clinical frequencies for a comma separated list of concepts
        # e.g. /api/v1/query?service=omop&meta=singleConceptFreq&q=4196636,437643
        if method == u'singleConceptFreq':
            concept_ids = u','.join([concept_id for concept_id in query.split(u',') if concept_id.strip().isdigit()])
            sql = '''select * from cohd.concept_counts
                      where concept_id in ({concept_ids})'''.format(concept_ids=concept_ids)

            print sql

            cur.execute(sql)
            results = cur.fetchall()

            for result in results:
                json_return.append({
                    u'concept_id': result[u'concept_id'],
                    u'concept_count': result[u'concept_count'],
                    u'concept_frequency': result[u'concept_frequency']
                })

        # Looks up observed clinical frequencies for a comma separated list of concepts
        # e.g. /api/v1/query?service=omop&meta=pairedConceptFreq&q=4196636,437643
        elif method == u'pairedConceptFreq':
            split_query = query.split(u',')
            if len(split_query) == 2:
                concept_id_1 = split_query[0].strip()
                concept_id_2 = split_query[1].strip()
                if concept_id_1.isdigit() and concept_id_2.isdigit():
                    sql = '''select * from cohd.concept_pair_counts
                              where (concept_id_1 = {concept_id_1} and concept_id_2 = {concept_id_2}) or 
                              (concept_id_1 = {concept_id_2} and concept_id_2 = {concept_id_1})'''.format(
                        concept_id_1=concept_id_1, concept_id_2=concept_id_2)

                    print sql

                    cur.execute(sql)
                    results = cur.fetchall()

                    for result in results:
                        json_return.append({
                            u'concept_id_1': result[u'concept_id_1'],
                            u'concept_id_2': result[u'concept_id_2'],
                            u'concept_count': result[u'concept_count'],
                            u'concept_frequency': result[u'concept_frequency']
                        })

        # Looks up observed clinical frequencies of all pairs of concepts given a concept id
        # e.g. /api/v1/query?service=omop&meta=associatedConceptFreq&q=4196636
        elif method == u'associatedConceptFreq':
            if query.isdigit():
                sql = '''select concept_count, concept_frequency, concept_name, domain_id,
                              if(concept_id_1 = {query}, concept_id_2, concept_id_1) as associated_concept_id                          
                          from cohd.concept_pair_counts, cohd.concept                          
                          where (concept_id_1 = {query} and concept_id_2 = concept.concept_id) 
                              or (concept_id_2 = {query} and concept_id_1 = concept.concept_id) 
                          order by concept_count desc'''.format(query=query)

                print sql

                cur.execute(sql)
                results = cur.fetchall()

                for result in results:
                    json_return.append({
                        u'concept_id': int(query),
                        u'associated_concept_id': result[u'associated_concept_id'],
                        u'concept_count': result[u'concept_count'],
                        u'concept_frequency': result[u'concept_frequency'],
                        u'associated_concept_name': result[u'concept_name'],
                        u'associated_concept_domain': result[u'domain_id']
                    })

        # Looks up observed clinical frequencies of all pairs of concepts given a concept id restricted by domain of the
        # associated concept_id
        # e.g. /api/v1/query?service=omop&meta=associatedConceptDomainFreq&concept_id=4196636&domain=Procedure
        elif method == u'associatedConceptDomainFreq':
            concept_id = query[u'concept_id']
            domain_id = query[u'domain_id']

            if concept_id.isdigit():
                sql = '''select concept_pair_counts.*, 
                              if(concept_id_1 = {concept_id}, c2.concept_id, c1.concept_id) as associated_concept_id,
	                          if(concept_id_1 = {concept_id}, c2.concept_name, c1.concept_name) as associated_concept_name
                          from cohd.concept_pair_counts, cohd.concept c1, cohd.concept c2
                          where c1.concept_id = concept_id_1 and c2.concept_id = concept_id_2 and 
                              ((concept_id_1 = {concept_id} and c2.domain_id = '{domain_id}') or 
                              (concept_id_2 = {concept_id} and c1.domain_id = '{domain_id}'))
                          order by concept_count desc'''.format(concept_id=concept_id, domain_id=domain_id)

                print sql

                cur.execute(sql)
                results = cur.fetchall()

                for result in results:
                    json_return.append({
                        u'concept_id': int(concept_id),
                        u'associated_concept_id': result[u'associated_concept_id'],
                        u'concept_count': result[u'concept_count'],
                        u'concept_frequency': result[u'concept_frequency'],
                        u'associated_concept_name': result[u'associated_concept_name']
                    })

    # print(json_return)

    cur.close()
    conn.close()

    json_result = {u"results": json_return}
    json_return = jsonify(json_result)

    return json_return
